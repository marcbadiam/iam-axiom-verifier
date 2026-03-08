#!/usr/bin/env python3
"""
engine.py — VerifierEngine (Main Facade)

Neuro-Symbolic Engine "2-in-1" for AWS auditing.
Orchestrates 4 offline layers: Intent (LLM) → Local State (JSON) → Compilation (IAM→SMT) → Inference (Z3).

Usage:
    from engine import VerifierEngine
    engine = VerifierEngine(data_dir="./data")
    result = engine.ask("Can junior devs delete the DB?")
    print(result.proof)
"""

import sys
from src.models import IntentType, LLMIntent, VerifierResult
from src.llm.router import translate_query
from src.aws.parser import (
    fetch_local_iam_policy,
    fetch_local_prices_and_quotas,
    parse_policy_statements,
    parse_resources,
    extract_allowed_instances,
)
from src.core.smt_solver import verify_access, optimize_blast_radius

class VerifierEngine:
    """
    Main IAM Axiom Verifier engine.
    Operates strictly offline using data frozen in the local data directory.

    Combines:
      - Module 1: Formal Access Verification (SAT Solver)
      - Module 2: Financial Blast Radius Optimization (ILP Solver)
    """

    def __init__(self, data_dir: str = "./data"):
        """
        Initializes the engine.
        Reads deterministic AWS state directly from local JSON files.
        """
        self.data_dir = data_dir
        print(f"🛡️ IAM Axiom Verifier initialized (Offline Mode | Data: {data_dir})")

    def ask(self, query: str) -> VerifierResult:
        """
        Main entry point.
        Processes a natural language query and returns a formal mathematical proof.
        """
        print(f"\n{'='*60}")
        print(f"  Query: \"{query}\"")
        print(f"{'='*60}")

        # --- Layer 1: Intent (LLM Router) ---
        print("\n[Layer 1/4] Semantic Router (LLM)")
        intent = translate_query(query)
        print(f"  → Intent: {intent.intent.value}")
        print(f"  → Target Role: {intent.target_role}")
        if intent.target_action:
            print(f"  → Action: {intent.target_action}")
        print(f"  → Regions: {intent.target_regions}")

        # --- Layer 2: Deterministic Fetcher (Local JSON) ---
        print("\n[Layer 2/4] Deterministic Fetcher (Local State)")
        # Notice we pass the data directory now, no API calls!
        policy = fetch_local_iam_policy(intent.target_role, self.data_dir)

        # --- Layer 3 & 4: Compilation + Inference ---
        if intent.intent == IntentType.ACCESS_VERIFICATION:
            return self._run_access_verification(policy, intent)
        else:
            return self._run_blast_radius(policy, intent)

    def _run_access_verification(self, policy: dict, intent: LLMIntent) -> VerifierResult:
        """Module 1: Formal Access Verification (SAT Solver)."""
        print("\n[Layer 3/4] IAM → SMT Compilation (Access Verification)")
        statements = parse_policy_statements(policy)
        
        print(f"  → {len(statements)} statements parsed")
        for s in statements:
            print(f"    • [{s.effect}] {s.sid}: {s.actions}")

        print("\n[Layer 4/4] Z3 Inference (SAT Solver)")
        result = verify_access(
            statements=statements,
            target_action=intent.target_action or "",
            target_resource=intent.target_resource or "*",
        )

        return result

    def _run_blast_radius(self, policy: dict, intent: LLMIntent) -> VerifierResult:
        """Module 2: Financial Blast Radius Optimization (ILP Solver)."""
        print("\n[Layer 3/4] IAM → SMT Compilation (Blast Radius)")

        # Get instance types allowed by IAM
        allowed_instances = extract_allowed_instances(policy)
        print(f"  → IAM allowed instances: {allowed_instances}")

        # Cross-reference with offline price catalog
        prices_data = fetch_local_prices_and_quotas(self.data_dir)
        resources, global_quota = parse_resources(prices_data, allowed_instances)

        print(f"  → Global quota: {global_quota} vCPUs")
        print("  → Processed resources:")
        for res in resources:
            status = "Allowed" if res.allowed else "Denied"
            print(f"    • {res.id:18} | {res.vcpu_cost:4} vCPU | "
                  f"${res.cost_per_hour:8.4f}/h | max {res.max_qty:3} | {status}")

        print("\n[Layer 4/4] Z3 Inference (ILP Solver)")
        result = optimize_blast_radius(
            resources=resources,
            global_quota=global_quota,
        )

        return result

# --- CLI DEMONSTRATION ---

def main():
    """CLI entry point. Runs a demonstration of both modules with local data."""
    import argparse

    parser = argparse.ArgumentParser(
        prog="engine.py",
        description="IAM Axiom Verifier — Offline Neuro-Symbolic Engine for AWS Security & FinOps",
    )
    parser.add_argument(
        "--data-dir",
        default="./data",
        help="Directory containing local AWS JSON fixtures"
    )
    args = parser.parse_args()

    engine = VerifierEngine(data_dir=args.data_dir)

    # --- Demo 1: Formal Access Verification ---
    print("\n" + "#" * 60)
    print("  DEMO 1: Formal Access Verification (SAT Solver)")
    print("#" * 60)

    r1 = engine.ask("Can junior developers delete the production database?")
    print(f"\n  Result: {r1.proof}")

    # --- Demo 2: Financial Blast Radius ---
    print("\n" + "#" * 60)
    print("  DEMO 2: Financial Blast Radius Optimization (ILP)")
    print("#" * 60)

    r2 = engine.ask("What is the financial blast radius if the data team is hacked?")
    print(f"\n  Result:\n  {r2.proof}")

    # --- Summary ---
    print("\n" + "=" * 60)
    print("  Audit Summary")
    print("=" * 60)
    print(f"  Module 1 (Access):       {r1.status.upper()}")
    print(f"  Module 2 (Blast Radius): {r2.status.upper()}")
    
    if r2.raw_model and r2.raw_model.get("max_damage_per_day"):
        print(f"  Max estimated damage:    ${r2.raw_model['max_damage_per_day']:,.0f}/day")
    print("=" * 60)

if __name__ == "__main__":
    main()