from typing import Literal

from pydantic import BaseModel, Field, field_validator


QualityFollowupStatus = Literal[
    "OPEN",
    "REVIEW_DUE",
    "IMPROVED",
    "UNCHANGED",
    "WORSENED",
    "CLOSED",
]
QualityFollowupReviewResult = Literal["IMPROVED", "UNCHANGED", "WORSENED"]
QualityFollowupReviewState = Literal[
    "WAITING_SCORECARD",
    "MISSING_DRIVER",
    "MISSING_METRIC",
    "COMPARABLE",
]


class QualityFollowupCreateRequest(BaseModel):
    transporter_external_id: str = Field(min_length=1, max_length=180)
    scorecard_id: str = Field(min_length=1, max_length=180)
    metric_key: str = Field(min_length=1, max_length=180)
    note: str = Field(min_length=1, max_length=1200)

    @field_validator("transporter_external_id", "scorecard_id", "metric_key", "note")
    @classmethod
    def strip_text(cls, value: str) -> str:
        return value.strip()


class QualityFollowupCloseRequest(BaseModel):
    note: str | None = Field(default=None, max_length=600)

    @field_validator("note")
    @classmethod
    def strip_note(cls, value: str | None) -> str | None:
        normalized = value.strip() if value else None
        return normalized or None


class QualityFollowupPeriod(BaseModel):
    scorecard_id: str
    year: int
    week: int = Field(ge=1, le=53)
    value: float | None = None


class QualityFollowupReview(BaseModel):
    state: QualityFollowupReviewState
    result: QualityFollowupReviewResult | None = None
    period: QualityFollowupPeriod | None = None
    delta: float | None = None
    delta_unit: str | None = None
    message: str


class QualityFollowupReadModel(BaseModel):
    id: str
    transporter_external_id: str
    workforce_member_id: int | None = None
    driver_display_name: str
    metric_key: str
    metric_label: str
    metric_unit: str | None = None
    baseline_direction: str
    baseline_status: str
    baseline: QualityFollowupPeriod
    note: str
    status: QualityFollowupStatus
    created_by: str
    created_at: str
    review: QualityFollowupReview
    closed_at: str | None = None
    closed_by: str | None = None
    close_note: str | None = None


class QualityFollowupSummary(BaseModel):
    open: int = Field(default=0, ge=0)
    review_due: int = Field(default=0, ge=0)
    improved: int = Field(default=0, ge=0)
    worsened: int = Field(default=0, ge=0)
    unchanged: int = Field(default=0, ge=0)
    closed: int = Field(default=0, ge=0)


class QualityFollowupList(BaseModel):
    items: list[QualityFollowupReadModel] = Field(default_factory=list)
    summary: QualityFollowupSummary = Field(default_factory=QualityFollowupSummary)


class QualityFollowupCreateResult(BaseModel):
    created: bool
    item: QualityFollowupReadModel

