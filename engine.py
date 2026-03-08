#!/usr/bin/env python3
"""
engine.py — VerifierEngine (Fachada Principal)

Motor Neuro-Simbólico "2 en 1" para auditoría AWS.
Orquesta las 4 capas: Intención (LLM) → Fetcher (AWS) → Compilación (IAM→SMT) → Inferencia (Z3).

Uso:
    from engine import VerifierEngine
    engine = VerifierEngine(aws_profile="produccion")
    resultado = engine.ask("¿Pueden los devs junior borrar la BD?")
    print(resultado.proof)
"""

import sys
import json
from src.models import IntentType, LLMIntent, VerifierResult
from src.llm.router import translate_query
from src.aws.parser import (
    fetch_iam_policy,
    fetch_prices_and_quotas,
    parse_policy_statements,
    parse_resources,
    extract_allowed_instances,
)
from src.core.smt_solver import verify_access, optimize_blast_radius


class VerifierEngine:
    """
    Motor principal IAM Axiom Verifier.

    Combina:
      - Módulo 1: Verificación Formal de Acceso (SAT Solver)
      - Módulo 2: Optimización de Blast Radius Financiero (ILP Solver)
    """

    def __init__(self, aws_profile: str = "default"):
        """
        Inicializa el motor.

        En producción, aws_profile configuraría boto3.Session(profile_name=...).
        En modo mock, se ignora.
        """
        self.aws_profile = aws_profile
        print(f"🛡️  IAM Axiom Verifier inicializado (perfil: {aws_profile})")

    def ask(self, query: str) -> VerifierResult:
        """
        Punto de entrada principal.
        Procesa una pregunta en lenguaje natural y devuelve un resultado formal.
        """
        print(f"\n{'='*60}")
        print(f"  📝 Consulta: \"{query}\"")
        print(f"{'='*60}")

        # ── Capa 1: Intención (LLM Router) ──────────────────────
        print(f"\n[Capa 1/4] 🧠 Enrutador Semántico (LLM)")
        intent = translate_query(query)
        print(f"  → Intención: {intent.intent.value}")
        print(f"  → Rol objetivo: {intent.target_role}")
        if intent.target_action:
            print(f"  → Acción: {intent.target_action}")
        print(f"  → Regiones: {intent.target_regions}")

        # ── Capa 2: Fetcher Determinista (AWS) ──────────────────
        print(f"\n[Capa 2/4] ☁️  Fetcher Determinista (AWS)")
        policy = fetch_iam_policy(intent.target_role)

        # ── Capa 3 & 4: Compilación + Inferencia ────────────────
        if intent.intent == IntentType.ACCESS_VERIFICATION:
            return self._run_access_verification(policy, intent)
        else:
            return self._run_blast_radius(policy, intent)

    def _run_access_verification(
        self, policy: dict, intent: LLMIntent
    ) -> VerifierResult:
        """Módulo 1: Verificación Formal de Acceso (SAT Solver)."""

        print(f"\n[Capa 3/4] 🔒 Compilación IAM → SMT (Verificación de Acceso)")
        statements = parse_policy_statements(policy)
        print(f"  → {len(statements)} statements parseados")
        for s in statements:
            print(f"    • [{s.effect}] {s.sid}: {s.actions}")

        print(f"\n[Capa 4/4] ⚡ Inferencia Z3 (SAT Solver)")
        result = verify_access(
            statements=statements,
            target_action=intent.target_action or "",
            target_resource=intent.target_resource or "*",
        )

        return result

    def _run_blast_radius(
        self, policy: dict, intent: LLMIntent
    ) -> VerifierResult:
        """Módulo 2: Optimización de Blast Radius Financiero (ILP Solver)."""

        print(f"\n[Capa 3/4] 💸 Compilación IAM → SMT (Blast Radius)")

        # Obtener instancias permitidas por IAM
        allowed_instances = extract_allowed_instances(policy)
        print(f"  → Instancias permitidas por IAM: {allowed_instances}")

        # Cruzar con catálogo de precios
        prices_data = fetch_prices_and_quotas()
        resources, global_quota = parse_resources(prices_data, allowed_instances)

        print(f"  → Cuota global: {global_quota} vCPUs")
        print(f"  → Recursos procesados:")
        for res in resources:
            status = "✓ Permitido" if res.allowed else "✗ Denegado"
            print(f"    • {res.id:18} | {res.vcpu_cost:4} vCPU | "
                  f"${res.cost_per_hour:8.4f}/h | máx {res.max_qty:3} | {status}")

        print(f"\n[Capa 4/4] ⚡ Inferencia Z3 (ILP Solver)")
        result = optimize_blast_radius(
            resources=resources,
            global_quota=global_quota,
        )

        return result


# ─── CLI ─────────────────────────────────────────────────────────────

def _run_demo():
    """Ejecuta una demostración de ambos módulos con datos locales."""

    engine = VerifierEngine(aws_profile="produccion")

    # ── Demo 1: Verificación Formal de Acceso ────────────────────
    print("\n" + "█" * 60)
    print("  DEMO 1: Verificación Formal de Acceso (SAT Solver)")
    print("█" * 60)

    r1 = engine.ask(
        "¿Pueden los desarrolladores junior borrar la base de datos de producción?"
    )
    print(f"\n  📋 Resultado: {r1.proof}")

    # ── Demo 2: Blast Radius Financiero ──────────────────────────
    print("\n" + "█" * 60)
    print("  DEMO 2: Optimización de Blast Radius Financiero (ILP)")
    print("█" * 60)

    r2 = engine.ask(
        "¿Cuál es el radio de explosión financiero si hackean al equipo de datos?"
    )
    print(f"\n  📋 Resultado:\n  {r2.proof}")

    # ── Resumen ──────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("  🏁 Resumen de Auditoría")
    print("=" * 60)
    print(f"  Módulo 1 (Acceso):       {r1.status.upper()}")
    print(f"  Módulo 2 (Blast Radius): {r2.status.upper()}")
    if r2.raw_model and r2.raw_model.get("max_damage_per_day"):
        print(f"  Daño máximo estimado:    ${r2.raw_model['max_damage_per_day']:,.0f}/día")
    print("=" * 60)


def _run_sync(args):
    """Sincroniza datos reales desde AWS (Cache-Refresh)."""
    from src.aws.fetcher import sync_aws_data

    regions = args.regions if args.regions else ["us-east-1"]
    profile = args.profile if args.profile else None

    sync_aws_data(
        regions=regions,
        aws_profile=profile,
    )


def main():
    """Punto de entrada CLI con subcomandos."""
    import argparse

    parser = argparse.ArgumentParser(
        prog="engine.py",
        description="🛡️  IAM Axiom Verifier — Motor Neuro-Simbólico para AWS Security & FinOps",
    )
    subparsers = parser.add_subparsers(dest="command")

    # Subcomando: demo
    subparsers.add_parser(
        "demo",
        help="Ejecutar la demostración con datos mock locales",
    )

    # Subcomando: sync-aws-data
    sync_parser = subparsers.add_parser(
        "sync-aws-data",
        help="Sincronizar precios y cuotas reales desde AWS (Cache-Refresh)",
    )
    sync_parser.add_argument(
        "--regions",
        nargs="+",
        default=["us-east-1"],
        help="Regiones AWS a consultar (default: us-east-1)",
    )
    sync_parser.add_argument(
        "--profile",
        default=None,
        help="Perfil de AWS CLI a usar (default: default)",
    )

    args = parser.parse_args()

    if args.command == "sync-aws-data":
        _run_sync(args)
    elif args.command == "demo":
        _run_demo()
    else:
        # Sin subcomando: ejecutar demo por defecto
        _run_demo()


if __name__ == "__main__":
    main()

