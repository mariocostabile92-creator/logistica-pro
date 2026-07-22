from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.domain.planning_conflicts import PlanningConflictResult
from app.domain.planning_readiness import PlanningReadinessResult
from app.runtime.planning_inputs import PlanningInputCompositionReport


class PlanningConflictReviewContext(BaseModel):
    model_config = ConfigDict(frozen=True)

    result: PlanningConflictResult
    readiness: PlanningReadinessResult
    composition_report: PlanningInputCompositionReport
    evaluated_at: datetime
