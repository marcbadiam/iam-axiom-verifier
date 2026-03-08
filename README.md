# IAM Axiom Verifier

**A Neuro-Symbolic Inference Engine for AWS Security & FinOps**

IAM Axiom Verifier is a **mathematical auditing** tool for AWS environments. It combines the flexibility of Large Language Models (LLMs) for semantic routing with the **absolute rigor** of SMT solvers (Formal Verification) to evaluate IAM policies.

Instead of relying on regular expressions, heuristics, or AI hallucinations, this engine translates the AWS state into a system of **inequalities and boolean logic**, mathematically demonstrating risk vectors.

---

## The Problem

- **AI Hallucinates:** LLMs cannot reliably reason about complex permission graphs or service quotas. An error in a security audit is **unacceptable**.

- **Static Calculators Fail:** Calculating the financial "Blast Radius" of a compromised credential is not a simple summation; it is a **combinatorial optimization problem (NP-Hard)** crossed with AWS quota constraints and IAM boolean logic.

---

## The Solution (Key Features)

This project implements a **"2-in-1" Neuro-Symbolic** architecture:

### Module 1: Formal Access Verifier (SAT Solver)

Translates AWS policies (explicit and implicit Allows/Denies) into **boolean theorems**. It demonstrates if a logical path exists for a role to access a critical resource.

The equation evaluated by Z3:

```
Permission_Granted = Has_Allow AND NOT Has_Explicit_Deny
```

### Module 2: Financial Blast Radius Optimizer (Max-SAT / ILP)

Cross-references IAM permissions with the AWS Pricing API and Service Quotas. It uses **Integer Linear Programming (ILP)** to find the exact combination of instances and regions an attacker would use to inflict maximum economic damage.

The objective function:

```
Maximize: C = Σ(cost_i × x_i × P_i)
Subject to:  Σ(vcpu_i × x_i × P_i) ≤ Q   ∧   0 ≤ x_i ≤ max_qty_i
```

---

## Architecture (How it works)

The system enforces a **strict boundary** between probabilistic reasoning (LLM) and deterministic execution (Z3):

```
┌─────────────────────────────────────────────────────────────┐
│                       User Question                         │
└───────────────────────────┬─────────────────────────────────┘
                            ▼
┌─────────────────────────────────────────────────────────────┐
│  Layer 1: Intent (LLM)                                      │
│  → Semantic Router: extracts role, action, intent           │
│  → Pydantic validates strict JSON (LLMIntent)               │
└───────────────────────────┬─────────────────────────────────┘
                            ▼
┌─────────────────────────────────────────────────────────────┐
│  Layer 2: Deterministic Fetcher (AWS / boto3)                │
│  → Downloads real IAM policies for the role                 │
│  → Obtains Service Quotas and public prices                 │
└───────────────────────────┬─────────────────────────────────┘
                            ▼
┌─────────────────────────────────────────────────────────────┐
│  Layer 3: Compilation (IAM → SMT)                           │
│  → Parses IAM JSON to typed PolicyStatements                │
│  → Cross-references permissions with price catalog          │
└──────────┬────────────────────────────────────┬─────────────┘
           ▼                                    ▼
┌────────────────────────┐    ┌──────────────────────────────┐
│  Layer 4a: SAT Solver  │    │  Layer 4b: ILP Solver        │
│  Access Verification   │    │  Financial Blast Radius      │
│  → UNSAT = Impossible  │    │  → SAT = Maximum cost        │
└────────────────────────┘    └──────────────────────────────┘
```

---

## Usage Examples

The package exposes a natural interface for the end user:

```python
from engine import VerifierEngine

engine = VerifierEngine(aws_profile="production")

# CASE 1: Formal Access Verification
result = engine.ask("Can junior developers delete the production database?")
print(result.proof)
# > UNSAT: Mathematically proven. The role 'DevTeam-Junior'
# > has an explicit Deny on 'rds:DeleteDBInstance'.

# CASE 2: Financial Damage Optimization (Blast Radius)
result = engine.ask("What is the financial blast radius if the data team is hacked?")
print(result.proof)
# > SAT (Max-Cost): Maximum damage is $45,200/day.
# > Optimal attack vector calculated by Z3:
# > Launch p4d.24xlarge instances (regional quota limit) in us-east-1.
```

---

## Installation and Execution

```bash
# 1. Create virtual environment
python3 -m venv venv
source venv/bin/activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Run the demo (both modules, local mock data)
python3 engine.py demo
```

---

## Synchronization with Real AWS (Cache-Refresh)

In production, the tool connects to **real AWS APIs** to obtain updated prices and quotas from the client account.

> [!IMPORTANT]
> The AWS Pricing API **only exists in `us-east-1`** and `ap-south-1`.
> The client always connects to `us-east-1` even if you query instance prices in Spain (`eu-south-2`) or Japan.

```bash
# Sync prices and quotas from AWS (requires configured credentials)
python3 engine.py sync-aws-data

# Specify regions and profile
python3 engine.py sync-aws-data --regions us-east-1 eu-west-1 --profile production
```

This command:
1. Connects to the **AWS Pricing API** (`us-east-1`) to obtain real On-Demand prices
2. Connects to the **AWS Service Quotas API** (by region) to obtain the vCPU limit (`L-1216C47A`)
3. Overwrites `data/aws_prices_quotas.json` with **100% real** data

Afterwards, the Z3 engine instantly reads from the local JSON — **deterministic and in milliseconds**.

---

## AWS Configuration (Least Privilege)

To connect to AWS securely, the tool uses a **dedicated IAM user with read-only permissions**. Never use your administrator user.

### 1. Create the permission policy

The file [`docs/iam-axiom-readonly-policy.json`](docs/iam-axiom-readonly-policy.json) contains the minimum necessary policy.

### What the policy DOES allow:

**IAM Role Audit (AuditIAMPolicies):**
- View the list of all roles in the account (ListRoles).
- View details of a specific role (GetRole).
- Read which policies are attached to those roles, whether they are inline or AWS managed (GetRolePolicy, ListRolePolicies, ListAttachedRolePolicies).
- View which instance profiles (used in EC2) are associated with a role.

**Price Query (QueryAWSPrices):**
- Use the AWS Pricing service to obtain details about costs and AWS product catalogs (GetProducts).

**Limit/Quota Query (QueryAWSQuotas):**
- Review the account's service limits (e.g., how many EC2 instances you can have) through the Service Quotas service.

### What it DOES NOT allow (Implicit restrictions)

It is important to understand that in AWS, what is not explicitly allowed is denied. Therefore, this policy:

- **Does not allow Modifying anything:** It has no "Write" permissions. It cannot create roles, delete policies, change permissions, or modify quotas.
- **Does not allow managing Users or Groups:** It only focuses on Roles. If you try to list the account's users (iam:ListUsers), it will fail.
- **Does not allow using other services:** It does not have access to S3 (view files), EC2 (start machines), RDS (view databases), etc.
- **Does not allow viewing real Billing:** Although it allows viewing the "price catalog," it does not allow viewing actual monthly bills or account consumption (it has no billing permissions).

> [!CAUTION]
> This policy is **read-only**. The tool cannot create, modify, or delete any resource in your AWS account.

### 2. Create the dedicated IAM user

```
AWS Console → IAM → Users → Create user
```

1. **Name:** `iam-axiom-auditor`
2. **Console access:** No (programmatic access only)
3. **Permissions:** `Attach policies directly` → `Create policy` → paste the content of [`iam-axiom-readonly-policy.json`](docs/iam-axiom-readonly-policy.json)
4. **Create Access Keys:** `Security credentials` tab → `Create access key` → select `Command Line Interface (CLI)`

AWS will give you an **Access Key ID** and a **Secret Access Key**.

### 3. Configure the local profile

```bash
aws configure --profile axiom-auditor
# AWS will ask for:
#   AWS Access Key ID:     ********
#   AWS Secret Access Key: ********
#   Default region name:   us-east-1
#   Default output format: json
```

### 4. Use the profile in the tool

```bash
# Sync with the least privilege profile
python3 engine.py sync-aws-data --profile axiom-auditor --regions us-east-1 eu-west-1
```

Internally, `boto3` uses that isolated profile:

```python
session = boto3.Session(profile_name='axiom-auditor')
pricing_client = session.client('pricing', region_name='us-east-1')
iam_client = session.client('iam')
```

---

## Project Structure

```
iam-axiom-verifier/
├── .env.example                 # Template for API Keys (OpenAI/Anthropic)
├── .gitignore                   # Ignores /venv, __pycache__, .env and local caches
├── LICENSE                      # Project license (e.g., MIT or Apache 2.0)
├── README.md                    # Main documentation
├── requirements.txt             # Strict dependencies (boto3, z3-solver, pydantic)
├── engine.py                    # Entrypoint: Main facade and CLI
│
├── src/                         # Source code
│   ├── __init__.py
│   ├── models.py                # Data Contracts (Pydantic v2)
│   ├── aws/                     # Layer 2: Deterministic Fetcher
│   │   ├── __init__.py
│   │   ├── fetcher.py           # Real client (Pricing + Quotas with boto3)
│   │   └── parser.py            # Parses IAM policies to typed objects
│   ├── core/                    # Layers 3-4: Mathematical Inference
│   │   ├── __init__.py
│   │   └── smt_solver.py        # SAT and ILP engines (Z3)
│   └── llm/                     # Layer 1: Probabilistic AI
│       ├── __init__.py
│       └── router.py            # Semantic Router (LLM Translator)
│
├── data/                        # Local cache and Mocks for development
│   ├── policy_devteam.json      
│   ├── policy_dataeng.json      
│   └── aws_prices_quotas.json   
│
└── docs/                        # Technical and security documentation
    └── iam-axiom-readonly-policy.json
```

---

## Tech Stack

| Component | Technology |
|---|---|
| **Logic Core** | `z3-solver` (Microsoft Research) |
| **Cloud Integration** | `boto3` (AWS SDK) |
| **AI Router** | OpenAI API / Anthropic API |
| **Data Contracts** | `pydantic` v2 |

