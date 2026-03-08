"""
models.py — Data Contracts (Pydantic v2)

Defines all typed structures that flow between the layers
of the neuro-symbolic engine.
"""

from enum import Enum
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field


# --- Intent Layer (LLM Router) ---

class IntentType(str, Enum):
    """Type of analysis requested by the user."""
    ACCESS_VERIFICATION = "access_verification"
    BLAST_RADIUS = "blast_radius"


class LLMIntent(BaseModel):
    """
    Validated output from the Semantic Router (LLM).
    Pydantic ensures a strict JSON contract.
    """
    intent: IntentType
    target_role: str = Field(..., description="Target IAM role (e.g., DevTeam-Junior)")
    target_action: Optional[str] = Field(None, description="AWS action to verify (e.g., rds:DeleteDBInstance)")
    target_resource: Optional[str] = Field(None, description="Target resource ARN (e.g., *)")
    target_regions: List[str] = Field(default_factory=lambda: ["us-east-1"])


# --- Deterministic Layer (AWS Fetcher) ---

class PolicyStatement(BaseModel):
    """Typed mirror of an IAM Policy Statement."""
    sid: Optional[str] = None
    effect: str  # "Allow" | "Deny"
    actions: List[str]
    resource: str = "*"
    condition: Optional[Dict[str, Any]] = None


class ResourceData(BaseModel):
    """AWS resource with its cost, vCPU, and if it is allowed by IAM."""
    id: str
    cost_per_hour: float
    vcpu_cost: int
    max_qty: int = 100
    allowed: bool = True


# --- Inference Layer (Unified Result) ---

class VerifierResult(BaseModel):
    """
    Unified result from both engine modules.
    - status: 'sat' | 'unsat'
    - proof: Human-readable explanation
    - raw_model: Raw data from the Z3 model
    """
    status: str
    proof: str
    raw_model: Optional[Dict[str, Any]] = None
