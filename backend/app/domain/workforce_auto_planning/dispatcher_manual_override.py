from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.domain.workforce_auto_planning.constraint_evaluation import (
    ConstraintEvaluation,
)


class DispatcherOverrideOperationType(str, Enum):
    ADD_ASSIGNMENT = "ADD_ASSIGNMENT"
    REMOVE_ASSIGNMENT = "REMOVE_ASSIGNMENT"
    REPLACE_ASSIGNMENT = "REPLACE_ASSIGNMENT"
    MOVE_ASSIGNMENT = "MOVE_ASSIGNMENT"
    MODIFY_ASSIGNMENT = "MODIFY_ASSIGNMENT"


class DispatcherManualOverride(BaseModel):
    model_config = ConfigDict(frozen=True, str_strip_whitespace=True)

    override_id: str = Field(min_length=1)
    organization_id: str = Field(min_length=1)
    proposal_id: str = Field(min_length=1)
    proposal_version: int = Field(gt=0, strict=True)
    assignment_id: str | None = Field(default=None, min_length=1)
    operation_type: DispatcherOverrideOperationType
    reason: str = Field(min_length=1)
    actor_id: str = Field(min_length=1)
    violations: tuple[ConstraintEvaluation, ...] = Field(default_factory=tuple)
    created_at: datetime

    @model_validator(mode="after")
    def validate_override_contract(self) -> "DispatcherManualOverride":
        if (
            self.operation_type
            != DispatcherOverrideOperationType.ADD_ASSIGNMENT
            and self.assignment_id is None
        ):
            raise ValueError(
                f"{self.operation_type.value} requires assignment_id"
            )
        if any(violation.passed for violation in self.violations):
            raise ValueError("violations can contain only failed constraints")
        return self
