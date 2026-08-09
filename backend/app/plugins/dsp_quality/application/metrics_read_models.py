from typing import Literal

from pydantic import BaseModel, Field


QualityThresholdStatus = Literal[
    "TARGET_MET",
    "BELOW_TARGET",
    "BELOW_MINIMUM",
    "NO_STANDARD",
    "NOT_EVALUABLE",
]
QualityImprovement = Literal["improved", "worsened", "unchanged", "unknown"]


class QualityMetricsPeriod(BaseModel):
    week: int | None = None
    year: int | None = None


class QualityMetricCurrent(BaseModel):
    raw_value: str | None = None
    numeric_value: float | None = None
    text_value: str | None = None
    value_state: str
    rating: str | None = None
    compliance_state: str | None = None


class QualityMetricStandardSet(BaseModel):
    id: str
    provider: str
    detected_source_version: str | None = None
    effective_from: str | None = None
    effective_to: str | None = None


class QualityMetricStandard(BaseModel):
    target: float | None = None
    minimum: float | None = None
    raw_target: str | None = None
    raw_minimum: str | None = None
    standard_available: bool = False
    standard_set: QualityMetricStandardSet | None = None


class QualityMetricPrevious(BaseModel):
    available: bool = False
    week: int | None = None
    year: int | None = None
    numeric_value: float | None = None
    text_value: str | None = None
    rating: str | None = None


class QualityMetricDelta(BaseModel):
    numeric_delta: float | None = None
    direction_adjusted_improvement: QualityImprovement = "unknown"


class QualityMetricStatus(BaseModel):
    target_status: QualityThresholdStatus
    minimum_status: QualityThresholdStatus


class QualityMetricReadItem(BaseModel):
    metric_key: str
    label: str
    category: str
    value_type: str
    unit: str | None = None
    direction: str
    current: QualityMetricCurrent
    standard: QualityMetricStandard
    previous: QualityMetricPrevious
    delta: QualityMetricDelta
    status: QualityMetricStatus


class QualityMetricsSummary(BaseModel):
    evaluatable: int = Field(default=0, ge=0)
    target_met: int = Field(default=0, ge=0)
    attention: int = Field(default=0, ge=0)


class QualityLatestMetrics(BaseModel):
    available: bool
    metrics_available: bool = False
    current_period: QualityMetricsPeriod = Field(default_factory=QualityMetricsPeriod)
    previous_period: QualityMetricsPeriod | None = None
    previous_available: bool = False
    summary: QualityMetricsSummary = Field(default_factory=QualityMetricsSummary)
    categories: list[str] = Field(default_factory=list)
    metrics: list[QualityMetricReadItem] = Field(default_factory=list)

