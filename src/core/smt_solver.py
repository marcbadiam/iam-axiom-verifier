"""
smt_solver.py — Inference Layer (Z3 Prover)

Contains TWO formal solvers:

  1. verify_access()         — SAT Solver (Formal Access Verification)
     Formula:  Permission_Granted = Has_Allow AND NOT Has_Explicit_Deny
     Evaluates if a role can execute an action on a resource.

  2. optimize_blast_radius() — Max-SAT / ILP Solver (Financial Blast Radius)
     Maximize: Σ(cost_i × x_i × P_i)
     Subject to: Σ(vcpu_i × x_i × P_i) ≤ Q  ∧  x_i ≤ max_qty_i
"""

import z3
import fnmatch
from typing import List, Dict, Any, Optional
from src.models import PolicyStatement, ResourceData, VerifierResult


# --- Module 1: Formal Access Verifier (SAT Solver) ---

def _action_matches(policy_action: str, target_action: str) -> bool:
    """
    Checks if a policy action covers the target action.
    Supports wildcards: 'rds:*' covers 'rds:DeleteDBInstance'.
    """
    return fnmatch.fnmatch(target_action.lower(), policy_action.lower())


def verify_access(
    statements: List[PolicyStatement],
    target_action: str,
    target_resource: str = "*",
) -> VerifierResult:
    """
    Formal Access Verifier using Z3 SAT Solver.

    Translates AWS IAM logic to the boolean equation:

        Permission_Granted = Has_Allow AND NOT Has_Explicit_Deny

    Where:
      - Has_Allow: at least one Statement with Effect=Allow exists
        covering the requested action and resource.
      - Has_Explicit_Deny: at least one Statement with Effect=Deny exists
        covering the requested action and resource.
      - If there is no Allow, Has_Allow = False (AWS implicit deny).

    Z3 evaluates if the model is Satisfiable (access possible)
    or Unsatisfiable (access mathematically impossible).
    """
    print(f"  [Z3] Compiling access theorem: '{target_action}' on '{target_resource}'")

    solver = z3.Solver()

    # --- Z3 Boolean Variables ---
    Has_Allow = z3.Bool('Has_Allow')
    Has_Explicit_Deny = z3.Bool('Has_Explicit_Deny')
    Permission_Granted = z3.Bool('Permission_Granted')

    # --- Central Axiom: Permission_Granted = Has_Allow AND NOT Has_Explicit_Deny
    solver.add(Permission_Granted == z3.And(Has_Allow, z3.Not(Has_Explicit_Deny)))

    # --- Evaluate IAM policies against the requested action ---
    has_allow = False
    has_deny = False
    matching_allow_sids = []
    matching_deny_sids = []

    for stmt in statements:
        action_covered = any(_action_matches(a, target_action) for a in stmt.actions)
        resource_covered = stmt.resource == "*" or stmt.resource == target_resource

        if action_covered and resource_covered:
            if stmt.effect == "Allow":
                has_allow = True
                matching_allow_sids.append(stmt.sid or "unnamed")
            elif stmt.effect == "Deny":
                has_deny = True
                matching_deny_sids.append(stmt.sid or "unnamed")

    # --- Fix discovered values as constraints ---
    solver.add(Has_Allow == has_allow)
    solver.add(Has_Explicit_Deny == has_deny)

    # --- We want to know if Permission_Granted can be True ---
    solver.add(Permission_Granted == True)

    print(f"  [Z3] Has_Allow = {has_allow} (statements: {matching_allow_sids})")
    print(f"  [Z3] Has_Explicit_Deny = {has_deny} (statements: {matching_deny_sids})")
    print(f"  [Z3] Equation: Permission_Granted = {has_allow} AND NOT {has_deny}")
    print(f"  [Z3] Solving constraints system...")

    result = solver.check()

    if result == z3.sat:
        # SAT: Access is possible
        proof_text = (
            f"SAT: Access POSSIBLE. The role has an active Allow for "
            f"'{target_action}' (via {matching_allow_sids}) "
            f"and there is NO explicit Deny blocking it."
        )
        return VerifierResult(
            status="sat",
            proof=proof_text,
            raw_model={
                "Has_Allow": has_allow,
                "Has_Explicit_Deny": has_deny,
                "Permission_Granted": True,
                "matching_allows": matching_allow_sids,
                "matching_denies": matching_deny_sids,
            },
        )
    else:
        # UNSAT: Mathematically impossible
        if has_deny and has_allow:
            reason = (
                f"has an Allow (via {matching_allow_sids}) BUT an explicit Deny "
                f"exists (via {matching_deny_sids}) that overrides it."
            )
        elif has_deny:
            reason = f"has an explicit Deny on '{target_action}' (via {matching_deny_sids})."
        else:
            reason = f"does not have any Allow for '{target_action}' (AWS implicit deny)."

        proof_text = (
            f"UNSAT: Mathematically proven. The role {reason}"
        )
        return VerifierResult(
            status="unsat",
            proof=proof_text,
            raw_model={
                "Has_Allow": has_allow,
                "Has_Explicit_Deny": has_deny,
                "Permission_Granted": False,
                "matching_allows": matching_allow_sids,
                "matching_denies": matching_deny_sids,
            },
        )


# --- Module 2: Financial Blast Radius Optimizer (ILP) ---

def optimize_blast_radius(
    resources: List[ResourceData],
    global_quota: int,
) -> VerifierResult:
    """
    Financial Blast Radius Optimizer using Z3 ILP (Max-SAT).

    Maximizes objective function:
        C = Σ (cost_i × x_i × P_i)     [total cost per hour]

    Subject to constraints:
        Σ (vcpu_i × x_i × P_i) ≤ Q     [global vCPU quota]
        0 ≤ x_i ≤ max_qty_i             [limits per instance type]
        P_i ∈ {0, 1}                    [allowed by IAM]
    """
    print(f"  [Z3] Initializing ILP engine for financial damage optimization...")

    optimizer = z3.Optimize()

    # Decision variables: x_i (quantity of each resource)
    x_vars = {}
    total_cost_cents = z3.IntVal(0)
    total_vcpu = z3.IntVal(0)

    for res in resources:
        var_name = f"x_{res.id.replace('.', '_')}"
        xi = z3.Int(var_name)
        x_vars[res.id] = xi

        # Domain: 0 ≤ x_i ≤ max_qty_i
        optimizer.add(xi >= 0)
        optimizer.add(xi <= res.max_qty)

        # P_i: Boolean derived from IAM policies
        Pi = 1 if res.allowed else 0

        # We work in cents (×10000) to avoid floating point in Z3
        cost_cents = int(res.cost_per_hour * 10000)

        # Accumulate objective and constraint
        total_cost_cents += (cost_cents * xi * Pi)
        total_vcpu += (res.vcpu_cost * xi * Pi)

    # Constraint: global vCPU quota
    optimizer.add(total_vcpu <= global_quota)

    # Objective function: Maximize total financial damage
    print(f"  [Z3] Objective function: Maximize Σ(cost_i × x_i × P_i)")
    print(f"  [Z3] Constraint: Σ(vcpu_i × x_i × P_i) ≤ {global_quota} vCPUs")
    optimizer.maximize(total_cost_cents)

    print(f"  [Z3] Solving Integer Linear Programming problem...")

    if optimizer.check() == z3.sat:
        model = optimizer.model()
        max_cost_val = model.eval(total_cost_cents)

        # Convert from cents to USD
        max_cost_hour = max_cost_val.as_long() / 10000.0 if z3.is_int_value(max_cost_val) else 0.0
        max_cost_day = max_cost_hour * 24

        # Extract optimal attack vector
        attack_vector = []
        for res in resources:
            qty = model.eval(x_vars[res.id])
            qty_val = qty.as_long() if z3.is_int_value(qty) else 0
            if qty_val > 0 and res.allowed:
                attack_vector.append({
                    "instance": res.id,
                    "quantity": qty_val,
                    "cost_hour": res.cost_per_hour * qty_val,
                    "vcpus": res.vcpu_cost * qty_val,
                })

        # Build human-readable proof
        vector_lines = []
        for v in attack_vector:
            vector_lines.append(
                f"    → {v['quantity']}× {v['instance']} "
                f"(${v['cost_hour']:,.2f}/h, {v['vcpus']} vCPUs)"
            )
        vector_str = "\n".join(vector_lines)

        proof_text = (
            f"SAT (Max-Cost): Maximum damage is ${max_cost_day:,.0f}/day "
            f"(${max_cost_hour:,.2f}/hour).\n"
            f"  Optimal attack vector calculated by Z3:\n{vector_str}"
        )

        return VerifierResult(
            status="sat",
            proof=proof_text,
            raw_model={
                "max_damage_per_hour": max_cost_hour,
                "max_damage_per_day": max_cost_day,
                "attack_vector": attack_vector,
                "global_quota_used": sum(v["vcpus"] for v in attack_vector),
            },
        )
    else:
        return VerifierResult(
            status="unsat",
            proof="UNSAT: No satisfiable model found for optimization.",
            raw_model={"max_damage_per_hour": 0.0, "attack_vector": []},
        )
