import json
from typing import Dict, Any, List, Tuple
from models import ResourceData

def load_json(filepath: str) -> Dict[str, Any]:
    with open(filepath, 'r') as f:
        return json.load(f)

def parse_environment(policy_path: str, limits_path: str) -> Tuple[List[ResourceData], int, Dict[str, Any]]:
    # 1. Lee un archivo JSON de políticas de AWS IAM.
    policy = load_json(policy_path)
    
    # 2. Lee diccionario/API local con Service Quotas y precios públicos de AWS.
    limits_and_prices = load_json(limits_path)
    
    global_quota = limits_and_prices.get("global_vcpu_quota", 32)
    roles_info = limits_and_prices.get("roles_info", {})
    
    # Extrae las acciones permitidas y restricciones
    # Buscamos 'ec2:RunInstances' en Action y extraemos los tipos de instancia permitidos.
    allowed_instances = []
    for statement in policy.get("Statement", []):
        if statement.get("Effect") == "Allow" and "ec2:RunInstances" in statement.get("Action", ""):
            condition = statement.get("Condition", {}).get("StringEquals", {})
            types = condition.get("ec2:InstanceType", [])
            if isinstance(types, str):
                allowed_instances.append(types)
            else:
                allowed_instances.extend(types)

    resources = []
    for res in limits_and_prices.get("resources", []):
        # P_i = 1 si está permitido por IAM, 0 si no
        allowed = res["id"] in allowed_instances or "*" in allowed_instances
        resources.append(
            ResourceData(
                id=res["id"],
                cost_per_hour=res["cost_per_hour"],
                vcpu_cost=res["vcpu"],
                allowed=allowed
            )
        )
        
    return resources, global_quota, roles_info
