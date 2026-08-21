from datetime import date as CalendarDate

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.domain.core_language import OperationalUnit, TimeWindow
from app.domain.workforce_auto_planning.constraint_evaluation import (
    ConstraintEvaluation,
)


class EligibilityDecisionNotice(BaseModel):
    model_config = ConfigDict(frozen=True, str_strip_whitespace=True)

    code: str = Field(min_length=1)
    message: str = Field(min_length=1)


class WorkforceEligibilityDecision(BaseModel):
    model_config = ConfigDict(frozen=True, str_strip_whitespace=True)

    demand_trace_id: str = Field(min_length=1)
    organization_id: str = Field(min_length=1)
    workforce_member_id: str = Field(min_length=1)
    operational_date: CalendarDate
    operational_unit: OperationalUnit
    time_window: TimeWindow
    capability_or_workload: str = Field(min_length=1)
    eligible: bool = Field(strict=True)
    evaluations: tuple[ConstraintEvaluation, ...] = Field(
        default_factory=tuple
    )
    exclusion_reasons: tuple[EligibilityDecisionNotice, ...] = Field(
        default_factory=tuple
    )
    warnings: tuple[EligibilityDecisionNotice, ...] = Field(
        default_factory=tuple
    )

    @model_validator(mode="after")
    def validate_decision(self) -> "WorkforceEligibilityDecision":
        if not self.operational_unit.external_identifier.strip():
            raise ValueError("operational_unit cannot be empty")
        if self.eligible and self.exclusion_reasons:
            raise ValueError(
                "eligible decision cannot include exclusion reasons"
            )
        return self
