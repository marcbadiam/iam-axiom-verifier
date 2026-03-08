"""
parser.py — Capa Determinista (AWS Fetcher)

En producción: boto3 descarga las políticas IAM reales y Service Quotas.
En este repositorio: carga los archivos JSON mock de data/.

Funciones:
  - fetch_iam_policy(role_name)       → dict (JSON de política IAM)
  - fetch_prices_and_quotas()         → dict (precios y cuotas)
  - parse_policy_statements(policy)   → List[PolicyStatement]
  - parse_resources(prices, allowed)  → List[ResourceData], global_quota
"""

import json
import os
from typing import Dict, Any, List, Tuple, Optional
from src.models import PolicyStatement, ResourceData

# Directorio de datos mock
DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "data")

# Mapeo de nombres de rol a archivos de política mock
ROLE_POLICY_MAP = {
    "DevTeam-Junior": "policy_devteam.json",
    "DataEng-Team": "policy_dataeng.json",
}


def _load_json(filepath: str) -> Dict[str, Any]:
    """Carga un archivo JSON desde disco."""
    with open(filepath, 'r') as f:
        return json.load(f)


def fetch_iam_policy(role_name: str) -> Dict[str, Any]:
    """
    Descarga la política IAM de un rol.

    En producción:
    ──────────────
    import boto3
    iam = boto3.client('iam', region_name='us-east-1')
    policies = iam.list_attached_role_policies(RoleName=role_name)
    # ... descargar y combinar todos los PolicyDocuments ...

    Mock: Carga el archivo JSON correspondiente al rol.
    """
    filename = ROLE_POLICY_MAP.get(role_name)
    if not filename:
        raise ValueError(f"Rol desconocido: '{role_name}'. Roles disponibles: {list(ROLE_POLICY_MAP.keys())}")

    filepath = os.path.join(DATA_DIR, filename)
    print(f"  [AWS] Cargando política IAM para '{role_name}' desde {filename}")
    return _load_json(filepath)


def fetch_prices_and_quotas() -> Dict[str, Any]:
    """
    Descarga los precios públicos y Service Quotas de AWS.

    En producción:
    ──────────────
    import boto3
    pricing = boto3.client('pricing', region_name='us-east-1')
    quotas = boto3.client('service-quotas', region_name='us-east-1')
    # ... consultar precios de instancias EC2 ...
    # ... consultar límite de vCPUs on-demand ...

    Mock: Carga aws_prices_quotas.json.
    """
    filepath = os.path.join(DATA_DIR, "aws_prices_quotas.json")
    print(f"  [AWS] Cargando precios y cuotas desde aws_prices_quotas.json")
    return _load_json(filepath)


def parse_policy_statements(policy: Dict[str, Any]) -> List[PolicyStatement]:
    """
    Convierte los Statement de una IAM Policy a objetos tipados PolicyStatement.
    Normaliza Action a lista si viene como string.
    """
    statements = []
    for stmt in policy.get("Statement", []):
        actions = stmt.get("Action", [])
        if isinstance(actions, str):
            actions = [actions]

        statements.append(PolicyStatement(
            sid=stmt.get("Sid"),
            effect=stmt.get("Effect", "Deny"),
            actions=actions,
            resource=stmt.get("Resource", "*"),
            condition=stmt.get("Condition"),
        ))

    return statements


def parse_resources(
    prices_data: Dict[str, Any],
    allowed_instances: List[str],
) -> Tuple[List[ResourceData], int]:
    """
    Cruza el catálogo de precios con los tipos de instancia permitidos por IAM.

    Retorna:
      - Lista de ResourceData con el flag 'allowed' calculado
      - Cuota global de vCPUs
    """
    global_quota = prices_data.get("global_vcpu_quota", 64)

    resources = []
    for res in prices_data.get("resources", []):
        # P_i = 1 si el tipo está en la lista permitida, 0 si no
        allowed = res["id"] in allowed_instances or "*" in allowed_instances
        resources.append(ResourceData(
            id=res["id"],
            cost_per_hour=res["cost_per_hour"],
            vcpu_cost=res["vcpu"],
            max_qty=res.get("max_qty", 100),
            allowed=allowed,
        ))

    return resources, global_quota


def extract_allowed_instances(policy: Dict[str, Any]) -> List[str]:
    """
    Extrae los tipos de instancia EC2 permitidos mirando las condiciones
    de ec2:RunInstances en los statements Allow.
    """
    allowed = []
    for stmt in policy.get("Statement", []):
        if stmt.get("Effect") != "Allow":
            continue
        actions = stmt.get("Action", [])
        if isinstance(actions, str):
            actions = [actions]
        if "ec2:RunInstances" not in actions:
            continue

        condition = stmt.get("Condition", {}).get("StringEquals", {})
        types = condition.get("ec2:InstanceType", [])
        if isinstance(types, str):
            allowed.append(types)
        else:
            allowed.extend(types)

    return allowed
