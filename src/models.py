"""
src/models.py

Data Contracts for IAM Axiom Verifier.
Uses Pydantic v2 to guarantee strict typing between the LLM intent, 
the parsed AWS state, and the Z3 SMT solver.
"""

from enum import Enum
from typing import List, Optional, Any, Dict
from pydantic import BaseModel, Field, ConfigDict

# ==========================================
# 1. LAYER 1: LLM INTENT MODELS
# ==========================================

class IntentType(str, Enum):
    """The two core mathematical modules of the engine."""
    ACCESS_VERIFICATION = "ACCESS_VERIFICATION"
    BLAST_RADIUS = "BLAST_RADIUS"
    UNKNOWN = "UNKNOWN"

class LLMIntent(BaseModel):
    """
    The strictly formatted JSON output expected from the LLM Semantic Router.
    """
    model_config = ConfigDict(extra='ignore')

    intent: IntentType = Field(
        ..., 
        description="The mathematical module to route the query to."
    )
    target_role: str = Field(
        ..., 
        description="The exact IAM Role name the user is asking about."
    )
    target_action: Optional[str] = Field(
        None, 
        description="The specific AWS action (e.g., 'rds:DeleteDBInstance'). Null for blast radius."
    )
    target_resource: Optional[str] = Field(
        "*", 
        description="The specific AWS resource ARN. Defaults to '*' if not specified."
    )
    target_regions: List[str] = Field(
        default_factory=lambda: ["us-east-1"], 
        description="AWS regions involved in the query."
    )

# ==========================================
# 2. LAYER 2 & 3: AWS STATE PARSING MODELS
# ==========================================

class PolicyStatement(BaseModel):
    """
    Represents a single block within an IAM Policy Document.
    """
    sid: str = Field(default="UnnamedStatement")
    effect: str = Field(..., description="Either 'Allow' or 'Deny'")
    actions: List[str] = Field(..., description="List of AWS API actions")
    resources: List[str] = Field(..., description="List of AWS resource ARNs")

class ResourceData(BaseModel):
    """
    Represents a compute resource (EC2) with its financial and technical weight.
    Used by the ILP Solver for the Blast Radius calculation.
    """
    id: str = Field(..., description="Instance type (e.g., 'p4d.24xlarge')")
    vcpu_cost: int = Field(..., description="Number of vCPUs consumed per instance")
    cost_per_hour: float = Field(..., description="Price in USD per hour")
    max_qty: int = Field(..., description="Maximum physical instances allowed per region")
    allowed: bool = Field(False, description="Whether the IAM policy allows launching this")

# ==========================================
# 3. LAYER 4: INFERENCE RESULT MODELS
# ==========================================

class VerifierResult(BaseModel):
    """
    The final unified output of the VerifierEngine.
    """
    status: str = Field(..., description="'SAT', 'UNSAT', or 'ERROR'")
    proof: str = Field(..., description="Human-readable explanation of the mathematical proof.")
    raw_model: Optional[Dict[str, Any]] = Field(
        None, 
        description="The raw output variables from the Z3 solver (e.g., optimal attack vector)."
    )