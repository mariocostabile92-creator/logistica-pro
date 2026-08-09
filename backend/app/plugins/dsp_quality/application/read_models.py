from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field


class QualityLatestScorecard(BaseModel):
    id: str
    revision_id: str
    dsp_identifier: str
    station: str
    reported_week: int = Field(ge=1, le=53)
    reported_year: int
    geography: str | None = None
    source_provider: str


class QualityLatestRevision(BaseModel):
    imported_at: datetime
    imported_by: str | None = None
    source_filename: str
    detected_template_version: str | None = None
    rank: int | None = None
    rank_wow_declared: int | None = None
    overall_score: Decimal | None = None
    overall_standing: str | None = None
    active_number: int = Field(default=1, ge=1)
    revision_count: int = Field(default=1, ge=1)


class QualityLatestSection(BaseModel):
    section_key: str
    label: str
    standing: str


class QualityLatestFocusArea(BaseModel):
    position: int
    metric_key: str | None = None
    source_label: str


class QualityLatestCounts(BaseModel):
    dsp_metrics: int = 0
    transporter_rows: int = 0
    working_hour_exceptions: int = 0
    mapped_transporters: int = 0
    unmapped_transporters: int = 0
    ambiguous_transporters: int = 0


class QualityLatestStandardSet(BaseModel):
    available: bool = False
    id: str | None = None
    provider: str | None = None
    version: str | None = None
    effective_from: str | None = None
    effective_to: str | None = None


class QualityLatestOverview(BaseModel):
    available: bool
    scorecard: QualityLatestScorecard | None = None
    revision: QualityLatestRevision | None = None
    sections: list[QualityLatestSection] = Field(default_factory=list)
    focus_areas: list[QualityLatestFocusArea] = Field(default_factory=list)
    counts: QualityLatestCounts = Field(default_factory=QualityLatestCounts)
    standard_set: QualityLatestStandardSet = Field(default_factory=QualityLatestStandardSet)
