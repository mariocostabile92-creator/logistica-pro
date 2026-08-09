from datetime import datetime
from decimal import Decimal
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, model_validator


class QualityRevisionStatus(str, Enum):
    IMPORTED = "imported"
    VALIDATED = "validated"
    ACTIVE = "active"
    SUPERSEDED = "superseded"
    REJECTED = "rejected"


class QualityValueState(str, Enum):
    PRESENT = "PRESENT"
    NOT_AVAILABLE = "NOT_AVAILABLE"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    MISSING = "MISSING"


class QualityValueType(str, Enum):
    PERCENTAGE = "percentage"
    DPMO = "dpmo"
    SCORE = "score"
    COUNT = "count"
    RATE = "rate"
    CATEGORICAL = "categorical"
    COMPLIANCE_STATE = "compliance_state"


class QualityDirection(str, Enum):
    HIGHER_IS_BETTER = "HIGHER_IS_BETTER"
    LOWER_IS_BETTER = "LOWER_IS_BETTER"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class QualityMetricScope(str, Enum):
    DSP = "dsp"
    TRANSPORTER = "transporter"
    BOTH = "both"


class QualityMappingStatus(str, Enum):
    MATCHED = "MATCHED"
    UNMAPPED = "UNMAPPED"
    AMBIGUOUS = "AMBIGUOUS"


class QualityScorecard(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    organization_id: str
    source_provider: str
    dsp_identifier: str
    station: str
    reported_year: int
    reported_week: int = Field(ge=1, le=53)
    geography: str | None = None
    active_revision_id: str | None = None
    created_at: datetime
    updated_at: datetime


class QualityScorecardRevision(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    organization_id: str
    scorecard_id: str
    source_filename: str
    source_fingerprint_sha256: str
    parser_adapter: str
    parser_version: str
    detected_template_version: str | None = None
    imported_at: datetime
    imported_by: str
    status: QualityRevisionStatus
    source_attachment_reference: str | None = None
    rank: int | None = None
    rank_wow_declared: int | None = None
    overall_score: Decimal | None = None
    overall_standing: str | None = None
    raw_period_label: str | None = None
    active: bool = False
    standard_set_id: str | None = None
    working_hours_section_present: bool = False
    working_hours_exception_count: int = Field(default=0, ge=0)


class QualityMetricDefinition(BaseModel):
    model_config = ConfigDict(frozen=True)

    metric_key: str
    canonical_label: str
    category: str
    value_type: QualityValueType
    unit: str | None = None
    direction: QualityDirection
    scope: QualityMetricScope
    provider: str = "amazon"
    definition_version: str = "q1.v1"
    active: bool = True


class NormalizedQualityValue(BaseModel):
    model_config = ConfigDict(frozen=True)

    raw_value: str | None
    normalized_numeric_value: Decimal | None = None
    normalized_text_value: str | None = None
    value_state: QualityValueState
    rating: str | None = None
    compliance_state: str | None = None
    normalization_rule_version: str

    @model_validator(mode="after")
    def validate_presence(self):
        if self.value_state is not QualityValueState.PRESENT and (
            self.normalized_numeric_value is not None
            or self.normalized_text_value is not None
        ):
            raise ValueError("Missing values cannot expose normalized content.")
        return self


class QualityMetricObservation(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    revision_id: str
    metric_key: str
    value: NormalizedQualityValue
    source_page: int | None = None
    source_table: str | None = None
    source_row: str | None = None
    source_column: str | None = None
    extracted_label: str | None = None


class QualitySectionStanding(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    revision_id: str
    section_key: str
    section_label: str
    standing: str
    source_page: int | None = None


class QualityTransporterRow(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    revision_id: str
    transporter_external_id: str
    row_index: int = Field(ge=1)
    workforce_member_id: int | None = None
    mapping_status: QualityMappingStatus = QualityMappingStatus.UNMAPPED
    source_page: int | None = None
    raw_row_fingerprint: str | None = None


class QualityTransporterObservation(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    transporter_row_id: str
    metric_key: str
    value: NormalizedQualityValue
    source_page: int | None = None
    source_column: str | None = None


class WorkforceExternalIdentity(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    organization_id: str
    source: str
    external_id: str
    workforce_member_id: int | None = None
    status: QualityMappingStatus
    valid_from: str | None = None
    valid_to: str | None = None
    verified_by: str | None = None
    verified_at: datetime | None = None
    created_at: datetime
    updated_at: datetime

    @model_validator(mode="after")
    def validate_mapping(self):
        if self.status is QualityMappingStatus.MATCHED:
            if self.workforce_member_id is None:
                raise ValueError("MATCHED identities require a Workforce member.")
        elif self.workforce_member_id is not None:
            raise ValueError("Only MATCHED identities can reference Workforce.")
        return self


class QualityWorkingHourException(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    revision_id: str
    transporter_external_id: str
    daily_limit_exceeded_raw: str | None = None
    daily_limit_exceeded: bool | None = None
    weekly_limit_exceeded_raw: str | None = None
    weekly_limit_exceeded: bool | None = None
    under_offwork_limit_raw: str | None = None
    under_offwork_limit: bool | None = None
    work_day_limit_exceeded_raw: str | None = None
    work_day_limit_exceeded: bool | None = None
    wh_exception_raw: str | None = None
    wh_exception: bool | None = None
    source_page: int | None = None
    source_row: str | None = None


class QualityFocusArea(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    revision_id: str
    position: int = Field(ge=1)
    metric_key: str | None = None
    source_label: str
    source_page: int | None = None


class QualityStandardSet(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    provider: str
    geography_scope: str | None = None
    station_scope: str | None = None
    detected_source_version: str | None = None
    effective_from: str | None = None
    effective_to: str | None = None
    source_fingerprint: str
    created_at: datetime


class QualityStandardRule(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    standard_set_id: str
    metric_key: str
    target_value: Decimal | None = None
    minimum_value: Decimal | None = None
    unit: str | None = None
    direction: QualityDirection
    raw_target: str | None = None
    raw_minimum: str | None = None
