from datetime import date as CalendarDate
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

from app.domain.workforce_auto_planning.constraint_evaluation import (
    ConstraintEvidence,
)


class PlanningPreferenceOutcome(str, Enum):
    PREFERRED = "PREFERRED"
    NEUTRAL = "NEUTRAL"
    DEPRIORITIZED = "DEPRIORITIZED"


class PlanningPreferenceEvaluation(BaseModel):
    model_config = ConfigDict(frozen=True, str_strip_whitespace=True)

    code: str = Field(min_length=1)
    outcome: PlanningPreferenceOutcome
    priority: int = Field(ge=0, strict=True)
    message: str = Field(min_length=1)
    evidence: tuple[ConstraintEvidence, ...] = Field(default_factory=tuple)
    rule_origin: str = Field(min_length=1)


class WorkforcePlanningPreferenceSet(BaseModel):
    model_config = ConfigDict(frozen=True, str_strip_whitespace=True)

    workforce_member_id: str = Field(min_length=1)
    operational_date: CalendarDate
    evaluations: tuple[PlanningPreferenceEvaluation, ...] = Field(
        default_factory=tuple
    )
