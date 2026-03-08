from pydantic import BaseModel
from typing import List, Optional

class LLMHypothesis(BaseModel):
    target_role: str
    target_regions: List[str]
    assume_role_chain_allowed: bool
    budget_threshold_warning: Optional[float] = None

class ResourceData(BaseModel):
    id: str
    cost_per_hour: float
    vcpu_cost: int
    allowed: bool
