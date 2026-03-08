"""
smt_solver.py — Capa de Inferencia (Z3 Prover)

Contiene DOS solucionadores formales:

  1. verify_access()         — SAT Solver (Verificación Formal de Acceso)
     Fórmula:  Permiso_Concedido = Hay_Allow AND NOT Hay_Deny_Explicito
     Evalúa si un rol puede ejecutar una acción sobre un recurso.

  2. optimize_blast_radius() — Max-SAT / ILP Solver (Blast Radius Financiero)
     Maximiza: Σ(cost_i × x_i × P_i)
     Sujeto a: Σ(vcpu_i × x_i × P_i) ≤ Q  ∧  x_i ≤ max_qty_i
"""

import z3
import fnmatch
from typing import List, Dict, Any, Optional
from src.models import PolicyStatement, ResourceData, VerifierResult


# ─── Módulo 1: Verificador Formal de Accesos (SAT Solver) ───────────

def _action_matches(policy_action: str, target_action: str) -> bool:
    """
    Comprueba si una acción de política cubre la acción objetivo.
    Soporta wildcards: 'rds:*' cubre 'rds:DeleteDBInstance'.
    """
    return fnmatch.fnmatch(target_action.lower(), policy_action.lower())


def verify_access(
    statements: List[PolicyStatement],
    target_action: str,
    target_resource: str = "*",
) -> VerifierResult:
    """
    Verificador Formal de Acceso usando Z3 SAT Solver.

    Traduce la lógica IAM de AWS a la ecuación booleana:

        Permiso_Concedido = Hay_Allow AND NOT Hay_Deny_Explicito

    Donde:
      - Hay_Allow: existe al menos un Statement con Effect=Allow
        que cubra la acción y recurso solicitados.
      - Hay_Deny_Explicito: existe al menos un Statement con Effect=Deny
        que cubra la acción y recurso solicitados.
      - Si no hay ningún Allow, Hay_Allow = False (deny implícito de AWS).

    Z3 evalúa si el modelo es Satisfactible (acceso posible)
    o Insatisfactible (acceso matemáticamente imposible).
    """
    print(f"  [Z3] Compilando teorema de acceso: '{target_action}' sobre '{target_resource}'")

    solver = z3.Solver()

    # ── Variables booleanas Z3 ───────────────────────────────────
    Hay_Allow = z3.Bool('Hay_Allow')
    Hay_Deny_Explicito = z3.Bool('Hay_Deny_Explicito')
    Permiso_Concedido = z3.Bool('Permiso_Concedido')

    # ── Axioma central: Permiso_Concedido = Hay_Allow AND NOT Hay_Deny_Explicito
    solver.add(Permiso_Concedido == z3.And(Hay_Allow, z3.Not(Hay_Deny_Explicito)))

    # ── Evaluar las políticas IAM contra la acción solicitada ────
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

    # ── Fijar los valores descubiertos como restricciones ────────
    solver.add(Hay_Allow == has_allow)
    solver.add(Hay_Deny_Explicito == has_deny)

    # ── Queremos saber si Permiso_Concedido puede ser True ───────
    solver.add(Permiso_Concedido == True)

    print(f"  [Z3] Hay_Allow = {has_allow} (statements: {matching_allow_sids})")
    print(f"  [Z3] Hay_Deny_Explicito = {has_deny} (statements: {matching_deny_sids})")
    print(f"  [Z3] Ecuación: Permiso_Concedido = {has_allow} AND NOT {has_deny}")
    print(f"  [Z3] Resolviendo sistema de restricciones...")

    result = solver.check()

    if result == z3.sat:
        # SAT: Es posible que se conceda el permiso
        proof_text = (
            f"⚠️ SAT: Acceso POSIBLE. El rol tiene un Allow activo para "
            f"'{target_action}' (vía {matching_allow_sids}) "
            f"y NO existe un Deny explícito que lo bloquee."
        )
        return VerifierResult(
            status="sat",
            proof=proof_text,
            raw_model={
                "Hay_Allow": has_allow,
                "Hay_Deny_Explicito": has_deny,
                "Permiso_Concedido": True,
                "matching_allows": matching_allow_sids,
                "matching_denies": matching_deny_sids,
            },
        )
    else:
        # UNSAT: Matemáticamente imposible
        if has_deny and has_allow:
            reason = (
                f"tiene un Allow (vía {matching_allow_sids}) PERO existe un Deny "
                f"explícito (vía {matching_deny_sids}) que lo anula."
            )
        elif has_deny:
            reason = f"tiene un Deny explícito en '{target_action}' (vía {matching_deny_sids})."
        else:
            reason = f"no tiene ningún Allow para '{target_action}' (deny implícito de AWS)."

        proof_text = (
            f"❌ UNSAT: Matemáticamente demostrado. El rol {reason}"
        )
        return VerifierResult(
            status="unsat",
            proof=proof_text,
            raw_model={
                "Hay_Allow": has_allow,
                "Hay_Deny_Explicito": has_deny,
                "Permiso_Concedido": False,
                "matching_allows": matching_allow_sids,
                "matching_denies": matching_deny_sids,
            },
        )


# ─── Módulo 2: Optimizador de Blast Radius Financiero (ILP) ─────────

def optimize_blast_radius(
    resources: List[ResourceData],
    global_quota: int,
) -> VerifierResult:
    """
    Optimizador de Radio de Explosión Financiera usando Z3 ILP (Max-SAT).

    Maximiza la función objetivo:
        C = Σ (cost_i × x_i × P_i)     [coste total por hora]

    Sujeto a las restricciones:
        Σ (vcpu_i × x_i × P_i) ≤ Q     [cuota global de vCPUs]
        0 ≤ x_i ≤ max_qty_i             [límites por tipo de instancia]
        P_i ∈ {0, 1}                    [permitido por IAM]
    """
    print(f"  [Z3] Inicializando motor ILP para optimización de daño financiero...")

    optimizer = z3.Optimize()

    # Variables de decisión: x_i (cantidad de cada recurso)
    x_vars = {}
    total_cost_cents = z3.IntVal(0)
    total_vcpu = z3.IntVal(0)

    for res in resources:
        var_name = f"x_{res.id.replace('.', '_')}"
        xi = z3.Int(var_name)
        x_vars[res.id] = xi

        # Dominio: 0 ≤ x_i ≤ max_qty_i
        optimizer.add(xi >= 0)
        optimizer.add(xi <= res.max_qty)

        # P_i: Booleano derivado de las políticas IAM
        Pi = 1 if res.allowed else 0

        # Trabajamos en céntimos (×10000) para evitar punto flotante en Z3
        cost_cents = int(res.cost_per_hour * 10000)

        # Acumular objetivo y restricción
        total_cost_cents += (cost_cents * xi * Pi)
        total_vcpu += (res.vcpu_cost * xi * Pi)

    # Restricción: cuota global de vCPUs
    optimizer.add(total_vcpu <= global_quota)

    # Función objetivo: Maximizar daño financiero total
    print(f"  [Z3] Función objetivo: Maximizar Σ(cost_i × x_i × P_i)")
    print(f"  [Z3] Restricción: Σ(vcpu_i × x_i × P_i) ≤ {global_quota} vCPUs")
    optimizer.maximize(total_cost_cents)

    print(f"  [Z3] Resolviendo problema de Programación Lineal Entera...")

    if optimizer.check() == z3.sat:
        model = optimizer.model()
        max_cost_val = model.eval(total_cost_cents)

        # Convertir de céntimos a USD
        max_cost_hour = max_cost_val.as_long() / 10000.0 if z3.is_int_value(max_cost_val) else 0.0
        max_cost_day = max_cost_hour * 24

        # Extraer vector de ataque óptimo
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

        # Construir prueba legible
        vector_lines = []
        for v in attack_vector:
            vector_lines.append(
                f"    → {v['quantity']}× {v['instance']} "
                f"(${v['cost_hour']:,.2f}/h, {v['vcpus']} vCPUs)"
            )
        vector_str = "\n".join(vector_lines)

        proof_text = (
            f"⚠️ SAT (Max-Cost): El daño máximo es de ${max_cost_day:,.0f}/día "
            f"(${max_cost_hour:,.2f}/hora).\n"
            f"  Vector de ataque óptimo calculado por Z3:\n{vector_str}"
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
            proof="❌ UNSAT: No se encontró un modelo satisfactible para la optimización.",
            raw_model={"max_damage_per_hour": 0.0, "attack_vector": []},
        )
