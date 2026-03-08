"""
aws_fetcher.py — Real AWS Client (Cache-Refresh Pattern)

Connects to real AWS APIs to synchronize data:
  1. AWS Pricing API  → On-Demand prices for EC2 instances
  2. Service Quotas   → Account vCPU limits

IMPORTANT:
  - The AWS Pricing API only exists in us-east-1 and ap-south-1.
    The client ALWAYS connects to us-east-1 regardless of the region
    of the queried instances.
  - Data is cached in data/aws_prices_quotas.json so that
    the Z3 engine can read them instantly without calling AWS every time.

Usage:
    python engine.py sync-aws-data                    # Default regions
    python engine.py sync-aws-data --regions us-east-1 eu-west-1
"""

import json
import os
import boto3
from typing import List, Dict, Any, Optional

# Data directory
DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "data")
CACHE_FILE = os.path.join(DATA_DIR, "aws_prices_quotas.json")

# Common instance types to query by default
DEFAULT_INSTANCE_TYPES = [
    "t3.micro",
    "t3.medium",
    "m5.large",
    "m5.xlarge",
    "c5.2xlarge",
    "r5.2xlarge",
    "p3.8xlarge",
    "p4d.24xlarge",
    "g5.48xlarge",
    "x1e.32xlarge",
]

# Mapping of AWS region code → human-readable name for the Pricing API
# The Pricing API uses "location" (human name), not the region code
REGION_DISPLAY_NAMES = {
    "us-east-1": "US East (N. Virginia)",
    "us-east-2": "US East (Ohio)",
    "us-west-1": "US West (N. California)",
    "us-west-2": "US West (Oregon)",
    "eu-west-1": "EU (Ireland)",
    "eu-west-2": "EU (London)",
    "eu-west-3": "EU (Paris)",
    "eu-central-1": "EU (Frankfurt)",
    "eu-south-1": "EU (Milan)",
    "eu-south-2": "EU (Spain)",
    "ap-south-1": "Asia Pacific (Mumbai)",
    "ap-northeast-1": "Asia Pacific (Tokyo)",
    "ap-southeast-1": "Asia Pacific (Singapore)",
    "ap-southeast-2": "Asia Pacific (Sydney)",
    "sa-east-1": "South America (Sao Paulo)",
}

# AWS quota code for "Running On-Demand Standard instances" (vCPUs)
VCPU_QUOTA_CODE = "L-1216C47A"


def _get_ec2_price(
    pricing_client,
    instance_type: str,
    region_display_name: str,
) -> Optional[float]:
    """
    Gets the hourly On-Demand price of an EC2 instance.

    NOTE: The pricing client MUST always be connected to us-east-1.
    The 'location' parameter is the human-readable region name (e.g., "EU (Ireland)"),
    NOT the region code (e.g., "eu-west-1").
    """
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
        response = pricing_client.get_products(
            ServiceCode="AmazonEC2",
            Filters=filters,
        )
    except Exception as e:
        print(f"    Error querying price for {instance_type}: {e}")
        return None

    if not response.get("PriceList"):
        return None

    # AWS returns a nested JSON (string inside dict)
    price_data = json.loads(response["PriceList"][0])

    # Navigate the JSON maze to extract the On-Demand price
    try:
        terms = price_data["terms"]["OnDemand"]
        term_id = list(terms.keys())[0]
        price_dimensions = terms[term_id]["priceDimensions"]
        dimension_id = list(price_dimensions.keys())[0]
        price_per_hour = float(price_dimensions[dimension_id]["pricePerUnit"]["USD"])
        return price_per_hour
    except (KeyError, IndexError):
        return None


def _get_instance_vcpus(
    ec2_client,
    instance_type: str,
) -> Optional[int]:
    """Gets the number of vCPUs for an instance type via DescribeInstanceTypes."""
    try:
        resp = ec2_client.describe_instance_types(InstanceTypes=[instance_type])
        if resp["InstanceTypes"]:
            return resp["InstanceTypes"][0]["VCpuInfo"]["DefaultVCpus"]
    except Exception as e:
        print(f"    Error obtaining vCPUs for {instance_type}: {e}")
    return None


def _get_vcpu_quota(quotas_client) -> Optional[float]:
    """
    Gets the account's On-Demand Standard vCPU quota.
    Quota code: L-1216C47A (Running On-Demand Standard instances).
    """
    try:
        response = quotas_client.get_service_quota(
            ServiceCode="ec2",
            QuotaCode=VCPU_QUOTA_CODE,
        )
        return response["Quota"]["Value"]
    except Exception as e:
        print(f"    Error obtaining vCPU quota: {e}")
        return None


def sync_aws_data(
    regions: Optional[List[str]] = None,
    instance_types: Optional[List[str]] = None,
    aws_profile: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Connects to AWS, downloads real prices and quotas, and updates
    the data/aws_prices_quotas.json file (local cache).

    Cache-Refresh Pattern:
      - Executed once with: python engine.py sync-aws-data
      - Data is cached on disk
      - The Z3 engine reads from the local JSON (response in milliseconds)

    Args:
        regions: List of region codes (e.g., ["us-east-1", "eu-west-1"])
        instance_types: Instance types to query
        aws_profile: AWS CLI profile name to use
    """
    if regions is None:
        regions = ["us-east-1"]
    if instance_types is None:
        instance_types = DEFAULT_INSTANCE_TYPES

    print("\n" + "=" * 60)
    print("  Synchronizing real data from AWS")
    print("=" * 60)

    # Create session with the specified profile
    session_kwargs = {}
    if aws_profile and aws_profile != "default":
        session_kwargs["profile_name"] = aws_profile
    session = boto3.Session(**session_kwargs)

    # --- 1. Pricing Client (ALWAYS us-east-1) ---
    print("\n  [1/3] Connecting to AWS Pricing API (us-east-1)...")
    pricing_client = session.client("pricing", region_name="us-east-1")

    # --- 2. Get prices and vCPUs for each instance ---
    print(f"  [2/3] Querying prices for {len(instance_types)} instance types...")

    # We use the first region to obtain instance metadata
    primary_region = regions[0]
    ec2_client = session.client("ec2", region_name=primary_region)
    region_display = REGION_DISPLAY_NAMES.get(primary_region, primary_region)

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
                "max_qty": 10,  # Conservative default value
            })
            print(f"${price:.4f}/h, {vcpus} vCPUs OK")
        else:
            print(f"not available in {primary_region}")

    # --- 3. Get quotas per region ---
    print(f"\n  [3/3] Querying Service Quotas per region...")

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
            regional_quotas[region] = 64  # Safe AWS default
            print(f"using default (64 vCPUs)")

    if global_quota == 0:
        global_quota = 64

    # --- Construct and save the JSON ---
    data = {
        "global_vcpu_quota": global_quota,
        "regional_quotas": regional_quotas,
        "resources": resources,
        "_metadata": {
            "source": "AWS Pricing API + Service Quotas API",
            "regions_queried": regions,
            "instance_types_queried": instance_types,
        },
    }

    os.makedirs(DATA_DIR, exist_ok=True)
    with open(CACHE_FILE, "w") as f:
        json.dump(data, f, indent=2)

    print(f"\n  Data synchronized and saved in data/aws_prices_quotas.json")
    print(f"     → {len(resources)} instances with real prices")
    print(f"     → Maximum quota: {global_quota} vCPUs")
    print(f"     → Regions: {regions}")
    print("=" * 60)

    return data
