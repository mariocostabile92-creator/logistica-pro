from enum import Enum
from typing import TypeAlias

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StrictFloat,
    StrictInt,
    StrictStr,
)


ConstraintEvidenceValue: TypeAlias = (
    StrictStr | StrictInt | StrictFloat | StrictBool | None
)


class ConstraintEvaluationCategory(str, Enum):
    HARD_CONSTRAINT = "HARD_CONSTRAINT"
    SOFT_CONSTRAINT = "SOFT_CONSTRAINT"
    WARNING = "WARNING"
    PREFERENCE = "PREFERENCE"


class ConstraintEvidence(BaseModel):
    model_config = ConfigDict(frozen=True, str_strip_whitespace=True)

    key: str = Field(min_length=1)
    value: ConstraintEvidenceValue


class ConstraintRemediation(BaseModel):
    model_config = ConfigDict(frozen=True, str_strip_whitespace=True)

    code: str = Field(min_length=1)
    message: str = Field(min_length=1)


class ConstraintEvaluation(BaseModel):
    model_config = ConfigDict(frozen=True, str_strip_whitespace=True)

    code: str = Field(min_length=1)
    category: ConstraintEvaluationCategory
    passed: bool = Field(strict=True)
    message: str = Field(min_length=1)
    evidence: tuple[ConstraintEvidence, ...] = Field(default_factory=tuple)
    rule_origin: str = Field(min_length=1)
    remediation: ConstraintRemediation | None = None
