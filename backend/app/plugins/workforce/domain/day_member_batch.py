from enum import Enum

from pydantic import BaseModel, Field

from app.plugins.workforce.domain.models import WorkforceDayStatus


class DayMemberOverwritePolicy(str, Enum):
    APPLY_TO_EMPTY_ONLY = "APPLY_TO_EMPTY_ONLY"
    REPLACE_SELECTED = "REPLACE_SELECTED"


class DayMemberBatchWarning(BaseModel):
    workforce_member_id: int
    code: str
    message: str
    existing_status_code: str | None = None


class DayMemberBatchResult(BaseModel):
    operational_date: str
    overwrite_policy: DayMemberOverwritePolicy
    requested_count: int = Field(ge=0)
    applied_count: int = Field(ge=0)
    skipped_count: int = Field(ge=0)
    overwritten_count: int = Field(ge=0)
    items: list[WorkforceDayStatus] = Field(default_factory=list)
    warnings: list[DayMemberBatchWarning] = Field(default_factory=list)
