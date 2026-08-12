from typing import Literal

from pydantic import BaseModel, Field


DriverAttentionStatus = Literal[
    "DA_ATTENZIONARE",
    "DA_MIGLIORARE",
    "IN_MIGLIORAMENTO",
    "STABILE",
    "SENZA_STORICO",
]


class QualityAttentionPeriod(BaseModel):
    week: int | None = None
    year: int | None = None


class QualityAttentionFocus(BaseModel):
    metric_key: str
    label: str
    current: float | None = None
    previous: float | None = None
    unit: str | None = None
    direction: str
    reason: str


class QualityDriverAttention(BaseModel):
    row_id: str
    transporter_external_id: str
    workforce_member_id: int | None = None
    display_name: str
    status: DriverAttentionStatus
    escalation_present: bool = False
    history_available: bool = False
    comparable_metrics: int = Field(default=0, ge=0)
    worsened_metrics: int = Field(default=0, ge=0)
    improved_metrics: int = Field(default=0, ge=0)
    unchanged_metrics: int = Field(default=0, ge=0)
    reasons: list[str] = Field(default_factory=list)
    focus: list[QualityAttentionFocus] = Field(default_factory=list)


class QualityDspAttention(BaseModel):
    metric_key: str
    label: str
    current: float | None = None
    previous: float | None = None
    delta: float | None = None
    unit: str | None = None
    direction: str
    standard_target: float | None = None
    standard_minimum: float | None = None
    status: str
    reason: str


class QualityAttentionStatusCounts(BaseModel):
    da_attenzionare: int = Field(default=0, ge=0)
    da_migliorare: int = Field(default=0, ge=0)
    in_miglioramento: int = Field(default=0, ge=0)
    stabile: int = Field(default=0, ge=0)
    senza_storico: int = Field(default=0, ge=0)


class QualityAttentionSummary(BaseModel):
    total_drivers: int = Field(default=0, ge=0)
    dsp_metrics_attention_count: int = Field(default=0, ge=0)
    drivers_attention_count: int = Field(default=0, ge=0)
    positive_trend_count: int = Field(default=0, ge=0)
    drivers_without_history_count: int = Field(default=0, ge=0)
    statuses: QualityAttentionStatusCounts = Field(
        default_factory=QualityAttentionStatusCounts,
    )


class QualityAttentionReadModel(BaseModel):
    available: bool
    current_period: QualityAttentionPeriod = Field(default_factory=QualityAttentionPeriod)
    previous_period: QualityAttentionPeriod | None = None
    previous_available: bool = False
    summary: QualityAttentionSummary = Field(default_factory=QualityAttentionSummary)
    dsp_signals: list[QualityDspAttention] = Field(default_factory=list)
    drivers: list[QualityDriverAttention] = Field(default_factory=list)
    driver_attention: list[QualityDriverAttention] = Field(default_factory=list)
    positive_trends: list[QualityDriverAttention] = Field(default_factory=list)

