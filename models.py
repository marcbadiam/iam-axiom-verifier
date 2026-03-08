"""
models.py — Contratos de Datos (Pydantic v2)

Define todas las estructuras tipadas que fluyen entre las capas
del motor neuro-simbólico.
"""

from enum import Enum
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field


# ─── Capa de Intención (LLM Router) ─────────────────────────────────

class IntentType(str, Enum):
    """Tipo de análisis solicitado por el usuario."""
    ACCESS_VERIFICATION = "access_verification"
    BLAST_RADIUS = "blast_radius"


class LLMIntent(BaseModel):
    """
    Salida validada del Enrutador Semántico (LLM).
    Pydantic garantiza un contrato JSON estricto.
    """
    intent: IntentType
    target_role: str = Field(..., description="Rol IAM objetivo (ej: DevTeam-Junior)")
    target_action: Optional[str] = Field(None, description="Acción AWS a verificar (ej: rds:DeleteDBInstance)")
    target_resource: Optional[str] = Field(None, description="ARN del recurso objetivo (ej: *)")
    target_regions: List[str] = Field(default_factory=lambda: ["us-east-1"])


# ─── Capa Determinista (AWS Fetcher) ────────────────────────────────

class PolicyStatement(BaseModel):
    """Espejo tipado de un Statement de IAM Policy."""
    sid: Optional[str] = None
    effect: str  # "Allow" | "Deny"
    actions: List[str]
    resource: str = "*"
    condition: Optional[Dict[str, Any]] = None


class ResourceData(BaseModel):
    """Recurso AWS con su coste, vCPU y si está permitido por IAM."""
    id: str
    cost_per_hour: float
    vcpu_cost: int
    max_qty: int = 100
    allowed: bool = True


# ─── Capa de Inferencia (Resultado Unificado) ───────────────────────

class VerifierResult(BaseModel):
    """
    Resultado unificado de ambos módulos del motor.
    - status: 'sat' | 'unsat'
    - proof: Explicación legible para humanos
    - raw_model: Datos crudos del modelo Z3
    """
    status: str
    proof: str
    raw_model: Optional[Dict[str, Any]] = None
