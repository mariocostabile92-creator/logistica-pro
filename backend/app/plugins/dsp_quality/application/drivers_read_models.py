from typing import Literal

from pydantic import BaseModel, Field


DriverMappingStatus = Literal["MATCHED", "UNMAPPED", "AMBIGUOUS"]
DriverMetricImprovement = Literal["improved", "worsened", "unchanged", "unknown"]


class QualityDriversPeriod(BaseModel):
    week: int | None = None
    year: int | None = None


class QualityDriverMetricValue(BaseModel):
    raw_value: str | None = None
    numeric_value: float | None = None
    text_value: str | None = None
    value_state: str = "MISSING"


class QualityDriverMetricPrevious(QualityDriverMetricValue):
    available: bool = False
    week: int | None = None
    year: int | None = None


class QualityDriverMetricDelta(BaseModel):
    numeric_delta: float | None = None
    direction_adjusted_improvement: DriverMetricImprovement = "unknown"


class QualityDriverMetricReadItem(BaseModel):
    metric_key: str
    label: str
    value_type: str
    unit: str | None = None
    direction: str
    current: QualityDriverMetricValue
    previous: QualityDriverMetricPrevious
    delta: QualityDriverMetricDelta
    status: Literal["NO_DRIVER_STANDARD"] = "NO_DRIVER_STANDARD"


class QualityDriverPerformanceRow(BaseModel):
    row_id: str
    row_index: int = Field(ge=1)
    transporter_external_id: str
    mapping_status: DriverMappingStatus
    workforce_member_id: int | None = None
    workforce_display_name: str | None = None
    metrics: list[QualityDriverMetricReadItem] = Field(default_factory=list)


class QualityDriversSummary(BaseModel):
    total: int = Field(default=0, ge=0)
    matched: int = Field(default=0, ge=0)
    unmapped: int = Field(default=0, ge=0)
    ambiguous: int = Field(default=0, ge=0)


class QualityLatestDrivers(BaseModel):
    available: bool
    drivers_available: bool = False
    current_period: QualityDriversPeriod = Field(default_factory=QualityDriversPeriod)
    previous_period: QualityDriversPeriod | None = None
    previous_available: bool = False
    summary: QualityDriversSummary = Field(default_factory=QualityDriversSummary)
    rows: list[QualityDriverPerformanceRow] = Field(default_factory=list)
