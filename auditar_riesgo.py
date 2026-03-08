#!/usr/bin/env python3
import sys
import json
from llm_translator import translate_query
from parser import parse_environment
from smt_solver import optimize_damage

def main():
    if len(sys.argv) < 2:
        print("Uso: python auditar_riesgo.py \"<Consulta en lenguaje natural>\"")
        sys.exit(1)
        
    query = sys.argv[1]
    
    print("\n=======================================================")
    print(" 🚀 Engine FinOps-SMT: Calculadora de Max-Damage AWS")
    print("=======================================================")
    
    print("\n[Módulo 1/3] Traducción de Hipótesis (LLM)")
    hypothesis = translate_query(query)
    print(f" -> Hipótesis Extraída (Estructura formal con Pydantic):\n{json.dumps(hypothesis.model_dump(), indent=2)}")
    
    print("\n[Módulo 2/3] Parseo Determinista del Entorno")
    resources, global_quota, roles_info = parse_environment("data/policy_devteam.json", "data/aws_prices_quotas.json")
    print(f" -> Límite Global de Cuota (vCPUs): {global_quota}")
    print(" -> Recursos procesados (IAM Policies + Precios Pùblicos):")
    for res in resources:
        status = "Permitido ✓" if res.allowed else "Denegado ✗"
        print(f"    - {res.id:15} | {res.vcpu_cost:3} vCPU | ${res.cost_per_hour:6.4f}/hora | {status}")
    
    print("\n[Módulo 3/3] Motor de Optimización Formal (Z3 Solver)")
    result = optimize_damage(hypothesis, resources, global_quota, roles_info)
    
    print("\n=======================================================")
    print(" 💥 RESULTADO SMT: VECTOR DE ATAQUE Y DAÑO MAXIMIZADO")
    print("=======================================================")
    if result["status"] == "sat":
        max_damage = result["max_damage_per_hour"]
        print(f" [$] Daño Financiero Máximo : ${max_damage:,.2f} / hora")
        print(f" [$] Daño Extrapolado       : ${max_damage * 24:,.2f} / día")
        print("\n [!] Combinación Exacta (Modelo Resultante):")
        for at in result["attack_vector"]:
            print(f"    -> Instanciar: {at}")
    else:
        print(" [!] UNSAT: No se encontró un modelo satisfactible.")

if __name__ == "__main__":
    main()
