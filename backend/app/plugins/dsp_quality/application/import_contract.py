from typing import Protocol

from pydantic import BaseModel, Field, model_validator

from app.plugins.dsp_quality.domain.models import QualityDirection


class QualitySourceInput(BaseModel):
    filename: str
    content: bytes
    media_type: str | None = None


class QualityIdentityInput(BaseModel):
    source_provider: str = "amazon"
    dsp_identifier: str
    station: str
    reported_year: int
    reported_week: int = Field(ge=1, le=53)
    geography: str | None = None


class QualityRevisionInput(BaseModel):
    source_filename: str
    parser_adapter: str
    parser_version: str
    detected_template_version: str | None = None
    source_attachment_reference: str | None = None
    rank: int | None = None
    rank_wow_declared: int | None = None
    overall_score: str | int | float | None = None
    overall_standing: str | None = None
    raw_period_label: str | None = None
    normalization_rule_version: str = "quality.v1"


class QualityMetricInput(BaseModel):
    metric_key: str
    raw_value: str | int | float | None
    rating: str | None = None
    compliance_state: str | None = None
    source_page: int | None = None
    source_table: str | None = None
    source_row: str | None = None
    source_column: str | None = None
    extracted_label: str | None = None


class QualitySectionInput(BaseModel):
    section_key: str
    section_label: str
    standing: str
    source_page: int | None = None


class QualityTransporterInput(BaseModel):
    transporter_external_id: str
    row_index: int = Field(ge=1)
    source_page: int | None = None
    raw_row_fingerprint: str | None = None
    metrics: list[QualityMetricInput]


class QualityWorkingHourExceptionInput(BaseModel):
    transporter_external_id: str
    daily_limit_exceeded: str | None = None
    weekly_limit_exceeded: str | None = None
    under_offwork_limit: str | None = None
    work_day_limit_exceeded: str | None = None
    wh_exception: str | None = None
    source_page: int | None = None
    source_row: str | None = None


class QualityWorkingHoursInput(BaseModel):
    section_present: bool
    exceptions: list[QualityWorkingHourExceptionInput] = Field(default_factory=list)


class QualityFocusAreaInput(BaseModel):
    position: int = Field(ge=1)
    metric_key: str | None = None
    source_label: str
    source_page: int | None = None


class QualityStandardRuleInput(BaseModel):
    metric_key: str
    target_value: str | int | float | None = None
    minimum_value: str | int | float | None = None
    unit: str | None = None
    direction: QualityDirection
    raw_target: str | None = None
    raw_minimum: str | None = None


class QualityStandardsInput(BaseModel):
    provider: str = "amazon"
    geography_scope: str | None = None
    station_scope: str | None = None
    detected_source_version: str | None = None
    effective_from: str | None = None
    effective_to: str | None = None
    rules: list[QualityStandardRuleInput] = Field(default_factory=list)


class QualityImportDocument(BaseModel):
    identity: QualityIdentityInput
    revision: QualityRevisionInput
    sections: list[QualitySectionInput] = Field(default_factory=list)
    dsp_metrics: list[QualityMetricInput] = Field(default_factory=list)
    transporter_rows: list[QualityTransporterInput] = Field(default_factory=list)
    working_hours: QualityWorkingHoursInput
    focus_areas: list[QualityFocusAreaInput] = Field(default_factory=list)
    standards: QualityStandardsInput | None = None
    warnings: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_unique_input(self):
        metric_keys = [item.metric_key for item in self.dsp_metrics]
        if len(metric_keys) != len(set(metric_keys)):
            raise ValueError("DSP metric keys must be unique per revision.")
        row_indexes = [item.row_index for item in self.transporter_rows]
        if len(row_indexes) != len(set(row_indexes)):
            raise ValueError("Transporter row indexes must be unique.")
        return self


class QualityImportResult(BaseModel):
    scorecard_id: str
    revision_id: str
    source_fingerprint_sha256: str
    idempotent: bool
    revision_created: bool
    previous_revision_id: str | None = None
    active_revision_id: str
    transporter_rows: int = 0
    warnings: list[str] = Field(default_factory=list)


class QualityScorecardAdapter(Protocol):
    adapter_id: str
    parser_version: str

    def supports(self, source: QualitySourceInput) -> bool: ...
    def detect_template(self, source: QualitySourceInput) -> str | None: ...
    def extract_identity(self, source: QualitySourceInput) -> QualityIdentityInput: ...
    def extract_dsp_metrics(self, source: QualitySourceInput) -> list[QualityMetricInput]: ...
    def extract_section_standings(self, source: QualitySourceInput) -> list[QualitySectionInput]: ...
    def extract_transporter_rows(self, source: QualitySourceInput) -> list[QualityTransporterInput]: ...
    def extract_working_hour_exceptions(self, source: QualitySourceInput) -> QualityWorkingHoursInput: ...
    def extract_focus_areas(self, source: QualitySourceInput) -> list[QualityFocusAreaInput]: ...
    def extract_standard_rules(self, source: QualitySourceInput) -> QualityStandardsInput | None: ...
    def extract_revision(self, source: QualitySourceInput) -> QualityRevisionInput: ...
