# 🛡️ IAM Axiom Verifier

**A Neuro-Symbolic Inference Engine for AWS Security & FinOps**

IAM Axiom Verifier is a **mathematical auditing** tool for AWS environments. It combines the flexibility of Large Language Models (LLMs) for semantic routing with the **absolute rigor** of SMT solvers (Formal Verification) to evaluate IAM policies.

Instead of relying on regular expressions, heuristics, or AI hallucinations, this engine translates the AWS state into a system of **inequalities and boolean logic**, mathematically demonstrating risk vectors.

---

## 🚨 The Problem

- **AI Hallucinates:** LLMs cannot reliably reason about complex permission graphs or service quotas. An error in a security audit is **unacceptable**.
- **Static Calculators Fail:** Calculating the financial "Blast Radius" of a compromised credential is not a simple summation; it is a **combinatorial optimization problem (NP-Hard)** crossed with AWS quota constraints and IAM boolean logic.

---

## ✨ The Solution (Key Features)

This project implements a **"2-in-1" Neuro-Symbolic** architecture:

### 🔒 Module 1: Formal Access Verifier (SAT Solver)
Translates AWS policies (explicit and implicit Allows/Denies) into **boolean theorems**. It demonstrates if a logical path exists for a role to access a critical resource.

The equation evaluated by Z3:
$$Permission\_Granted = Has\_Allow \land \neg Has\_Explicit\_Deny$$

### 💸 Module 2: Financial Blast Radius Optimizer (Max-SAT / ILP)
Cross-references IAM permissions with the offline AWS Pricing catalog and Service Quotas. It uses **Integer Linear Programming (ILP)** to find the exact combination of instances and regions an attacker would use to inflict maximum economic damage.

The objective function:
$$\max C = \sum_{i=1}^{n} (c_i \cdot x_i \cdot P_i)$$

Subject to:
$$\sum_{i=1}^{n} (v_i \cdot x_i \cdot P_i) \le Q \quad \land \quad 0 \le x_i \le max\_qty_i$$

---

## 🧠 Architecture (How it works)

The system enforces a **strict boundary** between probabilistic reasoning (LLM) and deterministic execution (Z3). Furthermore, it is completely **offline and air-gapped** from the AWS environment during the inference phase.

┌─────────────────────────────────────────────────────────────┐
│                       User Question                         │
└───────────────────────────┬─────────────────────────────────┘
                            ▼
┌─────────────────────────────────────────────────────────────┐
│  Layer 1: Intent (LLM - Gemini / OpenAI)                    │
│  → Semantic Router: extracts role, action, target resource  │
│  → Pydantic validates strict JSON (LLMIntent)               │
└───────────────────────────┬─────────────────────────────────┘
                            ▼
┌─────────────────────────────────────────────────────────────┐
│  Layer 2: Deterministic Fetcher (Local State)               │
│  → Reads frozen IAM policies from /data/ JSON fixtures      │
│  → Loads local Service Quotas and public prices             │
└───────────────────────────┬─────────────────────────────────┘
                            ▼
┌─────────────────────────────────────────────────────────────┐
│  Layer 3: Compilation (IAM → SMT)                           │
│  → Parses IAM JSON to typed PolicyStatements                │
│  → Cross-references permissions with offline price catalog  │
└──────────┬────────────────────────────────────┬─────────────┘
           ▼                                    ▼
┌────────────────────────┐    ┌──────────────────────────────┐
│  Layer 4a: SAT Solver  │    │  Layer 4b: ILP Solver        │
│  Access Verification   │    │  Financial Blast Radius      │
│  → UNSAT = Impossible  │    │  → SAT = Maximum cost        │
└────────────────────────┘    └──────────────────────────────┘

---

## 🔄 Standard Execution Flow (The 2-Step Process)

To adhere to strict security practices, data extraction is completely decoupled from the mathematical inference engine. 

### Step 1: Extract & Freeze AWS State (Requires Credentials)
First, an auditor uses the standalone extraction tool. This connects to AWS via read-only APIs, downloads the policies and quotas, and freezes them into local JSON files inside the data/ directory.

python tools/sync_aws.py --profile axiom-auditor --regions us-east-1 eu-west-1


### Step 2: Configure the LLM Router
The engine is **provider-agnostic**. Copy the `.env.example` file to `.env` and configure your preferred AI provider (Google Gemini or OpenAI) to power the Semantic Router. You can also enable a `USE_MOCK_LLM="true"` mode for completely offline, air-gapped testing.

### Step 3: Offline Mathematical Audit (Air-Gapped)
Once the data is frozen and the router is configured, you run the engine. The math engine strictly reads the local JSON state and applies mathematical proofs.

# Run the automated demonstration suite
python engine.py demo


---

## 💻 Usage Examples (Interactive CLI)

The package exposes an interactive natural language interface. You can ask complex security questions, and the LLM will translate them into exact parameters for the Z3 SMT solver.

**CASE 1: Formal Access Verification (Specific ARNs)**
You can query if a role has access to specific cloud resources:

python engine.py ask "Can junior developers delete the instance arn:aws:ec2:us-east-1:123456789012:instance/i-prod999?"

# > ❌ UNSAT: Mathematically proven. The role does not have any Allow 
# > for 'ec2:TerminateInstances' on that specific ARN.


**CASE 2: Financial Damage Optimization (Blast Radius)**
Ask the engine to calculate the worst-case scenario if a role is compromised:

python engine.py ask "If a hacker gets into the DataEng-Team account, what's the worst financial damage they can do?"

# > ⚠️ SAT (Max-Cost): Maximum damage is $13,729/day ($572.04/hour).
# > Optimal attack vector calculated by Z3:
# >   → 15× g5.48xlarge ($244.32/h, 2880 vCPUs)
# >   → 10× p4d.24xlarge ($327.72/h, 960 vCPUs)


---

## 🔐 AWS Configuration (Least Privilege)

To perform **Step 1 (Data Extraction)** securely, the tool uses a **dedicated IAM user with read-only permissions**. Never use your administrator user.

### 1. Create the permission policy
The file docs/iam-axiom-readonly-policy.json contains the minimum necessary policy.

**What the policy DOES allow:**
- **IAM Role Audit:** List roles, view role details, and read attached policies.
- **Price Query:** Use the AWS Pricing service to obtain details about EC2 costs.
- **Quota Query:** Review the account's service limits via Service Quotas.
- **EC2 Metadata:** Describe instance types to dynamically fetch vCPU limits.

**What it DOES NOT allow (Implicit restrictions):**
- **No Modifying anything:** It has zero "Write" permissions. 
- **No Data Plane Access:** It cannot access S3 objects, EC2 instances, or RDS databases.
- **No Billing Access:** It cannot view actual monthly bills or account consumption.

> [!CAUTION]
> This policy is **read-only**. The extraction tool cannot create, modify, or delete any resource in your AWS account.

### 2. Configure the local profile
Create an IAM User with the policy above, generate Access Keys for CLI, and run:

aws configure --profile axiom-auditor


---

## 📂 Project Structure

iam-axiom-verifier/
├── .env.example                 # Template for API Keys (Google Gemini / OpenAI)
├── .gitignore                   # Ignores /venv, __pycache__, .env and local caches
├── LICENSE                      # Project license
├── README.md                    # Main documentation
├── requirements.txt             # Strict dependencies
├── engine.py                    # Entrypoint: Offline Inference Engine & CLI
│
├── tools/                       # Utilities requiring internet/credentials
│   └── sync_aws.py              # Connects to AWS & freezes state to /data
│
├── src/                         # Core Source Code
│   ├── __init__.py
│   ├── models.py                # Data Contracts (Pydantic v2)
│   ├── aws/                     # Layer 2: Deterministic Fetcher (Local JSON)
│   │   ├── __init__.py
│   │   ├── fetcher.py           # Boto3 logic (Used by tools/sync_aws.py)
│   │   └── parser.py            # Parses local IAM JSON to typed objects
│   ├── core/                    # Layers 3-4: Mathematical Inference
│   │   ├── __init__.py
│   │   └── smt_solver.py        # SAT and ILP engines (Z3)
│   └── llm/                     # Layer 1: Probabilistic AI
│       ├── __init__.py
│       └── router.py            # Semantic Router (LLM Translator)
│
├── data/                        # Local cache and frozen Mocks
│   ├── policy_devteam.json      
│   ├── policy_dataeng.json      
│   └── aws_prices_quotas.json   
│
└── docs/                        # Technical and security documentation
    └── iam-axiom-readonly-policy.json


---

## 🔧 Tech Stack

| Component | Technology |
|---|---|
| **Logic Core** | `z3-solver` (Microsoft Research) |
| **Cloud Integration** | `boto3` (AWS SDK) |
| **AI Router** | Google GenAI SDK (`gemini-2.5-flash`) / OpenAI API |
| **Data Contracts** | `pydantic` v2 |
| **Environment** | `python-dotenv` |