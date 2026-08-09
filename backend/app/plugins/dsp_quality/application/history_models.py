from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field


class QualityScorecardHistoryItem(BaseModel):
    scorecard_id: str
    active_revision_id: str
    dsp_identifier: str
    station: str
    reported_week: int = Field(ge=1, le=53)
    reported_year: int
    geography: str | None = None
    overall_score: Decimal | None = None
    overall_standing: str | None = None
    rank: int | None = None
    rank_wow_declared: int | None = None
    imported_at: datetime
    source_filename: str
    revision_count: int = Field(ge=1)


class QualityScorecardHistory(BaseModel):
    items: list[QualityScorecardHistoryItem] = Field(default_factory=list)

