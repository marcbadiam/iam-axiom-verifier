"""
src/aws/fetcher.py — Real AWS Client (Cache-Refresh Pattern)

Connects to real AWS APIs to synchronize data:
  1. AWS Pricing API  → On-Demand prices for EC2 instances
  2. Service Quotas   → Account vCPU limits
  3. IAM API          → Custom Roles and Policies

IMPORTANT:
  - The AWS Pricing API only exists in us-east-1 and ap-south-1.
    The client ALWAYS connects to us-east-1.
  - Data is cached in the specified output directory so that
    the offline Z3 engine can read them instantly.
"""

import json
import os
import boto3
from typing import List, Dict, Any, Optional

# Common instance types to track for the Blast Radius module
DEFAULT_INSTANCE_TYPES = [
    "t3.micro", "m5.large", "c5.xlarge", "p4d.24xlarge", "g5.48xlarge"
]

# Mapping of AWS region code → human-readable name for the Pricing API
REGION_DISPLAY_NAMES = {
    "us-east-1": "US East (N. Virginia)",
    "eu-west-1": "EU (Ireland)",
    "eu-south-2": "Europe (Spain)", # Note: AWS sometimes uses "Europe" or "EU" depending on the region age
    "ap-northeast-1": "Asia Pacific (Tokyo)",
}

VCPU_QUOTA_CODE = "L-1216C47A"

def _get_ec2_price(pricing_client, instance_type: str, region_display_name: str) -> Optional[float]:
    """Gets the hourly On-Demand price of an EC2 instance."""
    filters = [
        {"Type": "TERM_MATCH", "Field": "ServiceCode", "Value": "AmazonEC2"},
        {"Type": "TERM_MATCH", "Field": "instanceType", "Value": instance_type},
        {"Type": "TERM_MATCH", "Field": "location", "Value": region_display_name},
        {"Type": "TERM_MATCH", "Field": "operatingSystem", "Value": "Linux"},
        {"Type": "TERM_MATCH", "Field": "preInstalledSw", "Value": "NA"},
        {"Type": "TERM_MATCH", "Field": "capacitystatus", "Value": "Used"},
        {"Type": "TERM_MATCH", "Field": "tenancy", "Value": "Shared"},
    ]

    try:
        response = pricing_client.get_products(ServiceCode="AmazonEC2", Filters=filters)
        if not response.get("PriceList"):
            return None

        price_data = json.loads(response["PriceList"][0])
        terms = price_data["terms"]["OnDemand"]
        term_id = list(terms.keys())[0]
        price_dimensions = terms[term_id]["priceDimensions"]
        dimension_id = list(price_dimensions.keys())[0]
        return float(price_dimensions[dimension_id]["pricePerUnit"]["USD"])
    except Exception as e:
        print(f"    ⚠️ Error querying price for {instance_type}: {e}")
        return None

def _get_instance_vcpus(ec2_client, instance_type: str) -> Optional[int]:
    """Gets the number of vCPUs for an instance type via DescribeInstanceTypes."""
    try:
        resp = ec2_client.describe_instance_types(InstanceTypes=[instance_type])
        if resp["InstanceTypes"]:
            return resp["InstanceTypes"][0]["VCpuInfo"]["DefaultVCpus"]
    except Exception as e:
        print(f"    ⚠️ Error obtaining vCPUs for {instance_type}: {e}")
    return None

def _get_vcpu_quota(quotas_client) -> Optional[float]:
    """Gets the account's On-Demand Standard vCPU quota."""
    try:
        response = quotas_client.get_service_quota(ServiceCode="ec2", QuotaCode=VCPU_QUOTA_CODE)
        return response["Quota"]["Value"]
    except Exception as e:
        print(f"    ⚠️ Error obtaining vCPU quota: {e}")
        return None

def _fetch_custom_iam_roles(session: boto3.Session) -> List[Dict[str, Any]]:
    """
    Fetches IAM roles based on Reachability Analysis:
    - Includes all custom roles (created by humans/Terraform).
    - Includes ANY role attached to an Instance Profile (Assumable by EC2),
      even if it's an AWS managed role.
    """
    print("\n  [4/4] Fetching IAM Roles (Reachability Analysis)...")
    iam_client = session.client('iam')
    roles_export = []
    
    try:
        # 1. Find all roles actively attached to compute resources (Instance Profiles)
        # This is exactly what you proposed: "roles assigned to at least 1 entity"
        active_compute_roles = set()
        print("    → Mapping Instance Profiles...")
        ip_paginator = iam_client.get_paginator('list_instance_profiles')
        for ip_page in ip_paginator.paginate():
            for profile in ip_page['InstanceProfiles']:
                for role in profile['Roles']:
                    active_compute_roles.add(role['RoleName'])
        
        # 2. Fetch the actual roles
        paginator = iam_client.get_paginator('list_roles')
        for page in paginator.paginate():
            for role in page['Roles']:
                role_name = role['RoleName']
                is_service_linked = "aws-service-role" in role['Path']
                
                # THE LOGIC: Keep it if it's attached to a machine OR if it's custom
                if is_service_linked and role_name not in active_compute_roles:
                    continue

                role_data = {
                    "RoleName": role_name,
                    "Arn": role['Arn'],
                    "InlinePolicies": [],
                    "AttachedPolicies": []
                }

                # Get Inline Policies
                inline_paginator = iam_client.get_paginator('list_role_policies')
                for inline_page in inline_paginator.paginate(RoleName=role_name):
                    for policy_name in inline_page['PolicyNames']:
                        policy_detail = iam_client.get_role_policy(
                            RoleName=role_name, PolicyName=policy_name
                        )
                        role_data["InlinePolicies"].append({
                            "PolicyName": policy_name,
                            "PolicyDocument": policy_detail['PolicyDocument']
                        })
                
                # Get Managed Policies (Attached)
                attached_paginator = iam_client.get_paginator('list_attached_role_policies')
                for attached_page in attached_paginator.paginate(RoleName=role_name):
                    for policy in attached_page['AttachedPolicies']:
                        # We just save the ARN. The Z3 compiler can look it up if needed later
                        role_data["AttachedPolicies"].append(policy['PolicyArn'])

                roles_export.append(role_data)
                
        print(f"    → {len(roles_export)} reachable roles fetched OK")
        
    except Exception as e:
        print(f"    ⚠️ IAM fetch failed. Error: {e}")

    return roles_export

def sync_aws_data(
    regions: List[str], 
    aws_profile: str, 
    output_dir: str,
    instance_types: Optional[List[str]] = None
) -> None:
    """
    Main orchestration function to fetch and freeze AWS state.
    Called by tools/sync_aws.py
    """
    if instance_types is None:
        instance_types = DEFAULT_INSTANCE_TYPES

    print("\n" + "=" * 60)
    print("  Synchronizing real data from AWS")
    print("=" * 60)

    session_kwargs = {}
    if aws_profile and aws_profile != "default":
        session_kwargs["profile_name"] = aws_profile
    session = boto3.Session(**session_kwargs)

    # --- 1. Pricing Client ---
    print("\n  [1/4] Connecting to AWS Pricing API (us-east-1)...")
    pricing_client = session.client("pricing", region_name="us-east-1")

    # --- 2. Prices and vCPUs ---
    print(f"  [2/4] Querying prices for {len(instance_types)} instance types...")
    primary_region = regions[0]
    ec2_client = session.client("ec2", region_name=primary_region)
    region_display = REGION_DISPLAY_NAMES.get(primary_region, "EU (Ireland)") # Fallback

    resources = []
    for instance_type in instance_types:
        print(f"    → {instance_type}...", end=" ", flush=True)
        price = _get_ec2_price(pricing_client, instance_type, region_display)
        vcpus = _get_instance_vcpus(ec2_client, instance_type)

        if price is not None and vcpus is not None:
            resources.append({
                "id": instance_type,
                "vcpu": vcpus,
                "cost_per_hour": round(price, 4),
                "max_qty": 10,
            })
            print(f"${price:.4f}/h, {vcpus} vCPUs OK")
        else:
            print(f"not available or error")

    # --- 3. Quotas ---
    print(f"\n  [3/4] Querying Service Quotas per region...")
    regional_quotas = {}
    global_quota = 0

    for region in regions:
        print(f"    → {region}...", end=" ", flush=True)
        quotas_client = session.client("service-quotas", region_name=region)
        quota = _get_vcpu_quota(quotas_client)

        if quota is not None:
            quota_int = int(quota)
            regional_quotas[region] = quota_int
            global_quota = max(global_quota, quota_int)
            print(f"{quota_int} vCPUs OK")
        else:
            regional_quotas[region] = 64
            print(f"using default (64 vCPUs)")

    if global_quota == 0:
        global_quota = 64

    # --- 4. IAM Roles ---
    roles_data = _fetch_custom_iam_roles(session)

    # --- Save to Disk ---
    os.makedirs(output_dir, exist_ok=True)
    
    # Save Prices & Quotas
    prices_data = {
        "global_vcpu_quota": global_quota,
        "regional_quotas": regional_quotas,
        "resources": resources,
        "_metadata": {
            "source": "AWS Pricing + Quotas API",
            "regions_queried": regions
        },
    }
    with open(os.path.join(output_dir, "aws_prices_quotas.json"), "w") as f:
        json.dump(prices_data, f, indent=2)

    # Save IAM Roles
    with open(os.path.join(output_dir, "iam_roles_export.json"), "w") as f:
        json.dump(roles_data, f, indent=2)

    print(f"\n  ✅ Data synchronized and frozen in {output_dir}/")
    print("=" * 60)