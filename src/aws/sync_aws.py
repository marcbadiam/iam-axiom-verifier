#!/usr/bin/env python3
"""
tools/sync_aws.py

Standalone extraction script for IAM Axiom Verifier.
Connects to AWS using a strictly read-only profile, downloads real IAM policies,
pricing catalogs, and Service Quotas, and freezes them as JSON files in the /data/ directory.

Usage:
    python tools/sync_aws.py --profile axiom-auditor --regions us-east-1 eu-west-1
"""

import argparse
import sys
import os

# Adjust path so it can be run from the project root
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from fetcher import sync_aws_data

def main():
    parser = argparse.ArgumentParser(
        description="Extracts AWS state (IAM, Pricing, Quotas) to local JSON fixtures."
    )
    parser.add_argument(
        "--profile", 
        default="default", 
        help="AWS CLI profile to use (must be read-only)"
    )
    parser.add_argument(
        "--regions", 
        nargs="+", 
        default=["us-east-1"],
        help="AWS regions to query for quotas and pricing"
    )
    parser.add_argument(
        "--output-dir", 
        default="./data", 
        help="Directory to save the JSON fixtures"
    )

    args = parser.parse_args()

    print(f"🔄 Connecting to AWS API (Profile: {args.profile})...")
    print(f"📍 Target Regions: {', '.join(args.regions)}")
    
    try:
        # This function handles all boto3 logic and saves the files
        sync_aws_data(
            regions=args.regions, 
            aws_profile=args.profile,
            output_dir=args.output_dir
        )
        print(f"\n✅ SUCCESS: AWS state successfully frozen in '{args.output_dir}/'")
        print("🔒 You can now run the VerifierEngine entirely offline.")
    except Exception as e:
        print(f"\n❌ ERROR: Failed to sync AWS data. Details: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()