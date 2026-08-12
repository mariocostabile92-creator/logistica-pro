from typing import Literal

from pydantic import BaseModel, Field

from app.plugins.dsp_quality.application.attention_read_models import (
    DriverAttentionStatus,
    QualityAttentionFocus,
)
from app.plugins.dsp_quality.application.drivers_read_models import (
    DriverMappingStatus,
    QualityDriverMetricValue,
)


HistoryMetricComparison = Literal[
    "IMPROVED",
    "WORSENED",
    "UNCHANGED",
    "NOT_COMPARABLE",
]


class QualityDriverHistoryPeriod(BaseModel):
    year: int
    week: int


class QualityDriverHistoryMetric(BaseModel):
    metric_key: str
    label: str
    unit: str | None = None
    direction: str
    value: QualityDriverMetricValue
    comparison: HistoryMetricComparison = "NOT_COMPARABLE"
    numeric_delta: float | None = None
    consecutive_worsening_comparisons: int = Field(default=0, ge=0)
    consecutive_improving_comparisons: int = Field(default=0, ge=0)
    recurring: bool = False
    recovery: bool = False
    status: Literal["NO_DRIVER_STANDARD"] = "NO_DRIVER_STANDARD"


class QualityDriverHistoryEntry(BaseModel):
    scorecard_id: str
    revision_id: str
    year: int
    week: int
    imported_at: str | None = None
    source_filename: str | None = None
    weekly_status: DriverAttentionStatus
    weekly_focus: list[QualityAttentionFocus] = Field(default_factory=list)
    reasons: list[str] = Field(default_factory=list)
    customer_escalations: float | None = None
    metrics: list[QualityDriverHistoryMetric] = Field(default_factory=list)


class QualityDriverHistoryTrend(BaseModel):
    metric_key: str
    label: str
    direction: str
    consecutive_worsening_comparisons: int = Field(default=0, ge=0)
    consecutive_improving_comparisons: int = Field(default=0, ge=0)
    recurring: bool = False
    recovery: bool = False


class QualityDriverHistorySummary(BaseModel):
    weeks_available: int = Field(default=0, ge=0)
    first_period: QualityDriverHistoryPeriod | None = None
    latest_period: QualityDriverHistoryPeriod | None = None
    current_status: DriverAttentionStatus | None = None
    current_focus: list[QualityAttentionFocus] = Field(default_factory=list)
    recurring_worsening_metrics: list[QualityDriverHistoryTrend] = Field(
        default_factory=list,
    )
    recurring_improving_metrics: list[QualityDriverHistoryTrend] = Field(
        default_factory=list,
    )
    recent_customer_escalations: float | None = None


class QualityDriverHistoryReadModel(BaseModel):
    available: bool
    transporter_external_id: str
    workforce_member_id: int | None = None
    workforce_display_name: str | None = None
    mapping_status: DriverMappingStatus = "UNMAPPED"
    source_provider: str | None = None
    dsp_identifier: str | None = None
    station: str | None = None
    anchor_scorecard_id: str | None = None
    anchor_period: QualityDriverHistoryPeriod | None = None
    summary: QualityDriverHistorySummary = Field(
        default_factory=QualityDriverHistorySummary,
    )
    metric_trends: list[QualityDriverHistoryTrend] = Field(default_factory=list)
    timeline: list[QualityDriverHistoryEntry] = Field(default_factory=list)
