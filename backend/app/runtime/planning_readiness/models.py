from pydantic import BaseModel, ConfigDict

from app.domain.planning_inputs import PlanningInputEnvelope
from app.domain.planning_readiness import PlanningReadinessResult


class PlanningReadinessEvaluationContext(BaseModel):
    model_config = ConfigDict(frozen=True)

    result: PlanningReadinessResult
    envelope: PlanningInputEnvelope | None = None
