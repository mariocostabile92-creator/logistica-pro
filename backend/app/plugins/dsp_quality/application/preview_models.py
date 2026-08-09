from decimal import Decimal
from enum import Enum

from pydantic import BaseModel, Field

from app.plugins.dsp_quality.domain.models import (
    QualityMappingStatus,
    QualityValueState,
)


class QualityImportAction(str, Enum):
    CREATE = "CREATE"
    NO_OP = "NO_OP"
    NEW_REVISION = "NEW_REVISION"


class QualityValidationMessage(BaseModel):
    code: str
    message: str


class QualityPreviewIdentity(BaseModel):
    dsp_identifier: str | None = None
    station: str | None = None
    reported_week: int | None = None
    reported_year: int | None = None
    rank: int | None = None
    rank_wow_declared: int | None = None
    overall_score: Decimal | None = None
    overall_standing: str | None = None
    raw_period_label: str | None = None
    geography: str | None = None
    geography_authoritative: bool = False
    detected_template_version: str | None = None


class QualityPreviewCounts(BaseModel):
    dsp_metrics_count: int = 0
    transporter_rows_count: int = 0
    working_hours_exception_count: int = 0
    focus_areas_count: int = 0
    standards_count: int = 0


class QualityPreviewMappingCounts(BaseModel):
    matched_transporters: int = 0
    unmapped_transporters: int = 0
    ambiguous_transporters: int = 0


class QualityTransporterMappingPreview(BaseModel):
    transporter_external_id: str
    status: QualityMappingStatus
    workforce_member_id: int | None = None


class QualityMetricPreview(BaseModel):
    metric_key: str
    raw_value: str | None = None
    normalized_numeric_value: Decimal | None = None
    normalized_text_value: str | None = None
    rating: str | None = None
    compliance_state: str | None = None
    value_state: QualityValueState


class QualitySectionPreview(BaseModel):
    section_key: str
    section_label: str
    standing: str


class QualityFocusPreview(BaseModel):
    position: int
    source_label: str
    metric_key: str | None = None


class QualityStandardPreview(BaseModel):
    metric_key: str
    raw_target: str | None = None
    raw_minimum: str | None = None
    source_page: int | None = None


class QualityPreviewValidation(BaseModel):
    errors: list[QualityValidationMessage] = Field(default_factory=list)
    warnings: list[QualityValidationMessage] = Field(default_factory=list)
    infos: list[QualityValidationMessage] = Field(default_factory=list)


class QualityPreviewIdempotency(BaseModel):
    fingerprint: str
    existing_scorecard: str | None = None
    existing_revision: str | None = None
    action: QualityImportAction | None = None


class QualityImportPreview(BaseModel):
    valid: bool
    preview_token: str | None = None
    identity: QualityPreviewIdentity
    counts: QualityPreviewCounts
    mapping: QualityPreviewMappingCounts
    transporter_mappings: list[QualityTransporterMappingPreview] = Field(default_factory=list)
    dsp_metrics: list[QualityMetricPreview] = Field(default_factory=list)
    section_standings: list[QualitySectionPreview] = Field(default_factory=list)
    focus_areas: list[QualityFocusPreview] = Field(default_factory=list)
    standards: list[QualityStandardPreview] = Field(default_factory=list)
    working_hours_section_present: bool = False
    validation: QualityPreviewValidation
    idempotency: QualityPreviewIdempotency


class QualityImportConfirmation(BaseModel):
    scorecard_id: str
    revision_id: str
    action: QualityImportAction
    idempotent: bool
    revision_created: bool
    previous_revision_id: str | None = None
    active_revision_id: str
    source_attachment_reference: str
    transporter_rows: int
    warnings: list[str] = Field(default_factory=list)
