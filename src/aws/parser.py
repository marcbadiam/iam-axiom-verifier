"""
parser.py — Deterministic Layer (AWS Fetcher)

In production: boto3 downloads the actual IAM policies and Service Quotas.
In this repository: loads mock JSON files from data/.

Functions:
  - fetch_iam_policy(role_name)       → dict (IAM policy JSON)
  - fetch_prices_and_quotas()         → dict (prices and quotas)
  - parse_policy_statements(policy)   → List[PolicyStatement]
  - parse_resources(prices, allowed)  → List[ResourceData], global_quota
"""

import json
import os
from typing import Dict, Any, List, Tuple, Optional
from src.models import PolicyStatement, ResourceData

# Mock data directory
DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "data")

# Mapping of role names to mock policy files
ROLE_POLICY_MAP = {
    "DevTeam-Junior": "policy_devteam.json",
    "DataEng-Team": "policy_dataeng.json",
}


def _load_json(filepath: str) -> Dict[str, Any]:
    """Loads a JSON file from disk."""
    with open(filepath, 'r') as f:
        return json.load(f)


def fetch_iam_policy(role_name: str) -> Dict[str, Any]:
    """
    Downloads the IAM policy for a role.

    In production:
    --------------
    import boto3
    iam = boto3.client('iam', region_name='us-east-1')
    policies = iam.list_attached_role_policies(RoleName=role_name)
    # ... download and combine all PolicyDocuments ...

    Mock: Loads the corresponding JSON file for the role.
    """
    filename = ROLE_POLICY_MAP.get(role_name)
    if not filename:
        raise ValueError(f"Unknown role: '{role_name}'. Available roles: {list(ROLE_POLICY_MAP.keys())}")

    filepath = os.path.join(DATA_DIR, filename)
    print(f"  [AWS] Loading IAM policy for '{role_name}' from {filename}")
    return _load_json(filepath)


def fetch_prices_and_quotas() -> Dict[str, Any]:
    """
    Downloads public prices and AWS Service Quotas.

    In production:
    --------------
    import boto3
    pricing = boto3.client('pricing', region_name='us-east-1')
    quotas = boto3.client('service-quotas', region_name='us-east-1')
    # ... query EC2 instance prices ...
    # ... query on-demand vCPU limits ...

    Mock: Loads aws_prices_quotas.json.
    """
    filepath = os.path.join(DATA_DIR, "aws_prices_quotas.json")
    print(f"  [AWS] Loading prices and quotas from aws_prices_quotas.json")
    return _load_json(filepath)


def parse_policy_statements(policy: Dict[str, Any]) -> List[PolicyStatement]:
    """
    Converts IAM Policy Statements to typed PolicyStatement objects.
    Normalizes Action to a list if it comes as a string.
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
    Cross-references the price catalog with the instance types allowed by IAM.

    Returns:
      - List of ResourceData with the calculated 'allowed' flag
      - Global vCPU quota
    """
    global_quota = prices_data.get("global_vcpu_quota", 64)

    resources = []
    for res in prices_data.get("resources", []):
        # allowed = True if the type is in the allowed list, False otherwise
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
    Extracts allowed EC2 instance types by looking at ec2:RunInstances conditions
    in the Allow statements.
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
