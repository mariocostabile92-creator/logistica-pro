from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


class IdentityConfidenceClass(str, Enum):
    EXACT = "EXACT"
    SUGGESTED = "SUGGESTED"
    UNRESOLVED = "UNRESOLVED"
    CONFLICT = "CONFLICT"


class IdentityEvidenceStatus(str, Enum):
    EXACT = "EXACT"
    SUGGESTED = "SUGGESTED"
    UNRESOLVED = "UNRESOLVED"
    CONFLICT = "CONFLICT"
    CONFLICT_WITH_VERIFIED_MAPPING = "CONFLICT_WITH_VERIFIED_MAPPING"
    ALREADY_VERIFIED = "ALREADY_VERIFIED"


class IdentitySourceMetadata(BaseModel):
    filename: str
    source_type: str
    source_reference: str
    sheet: str | None = None
    header_row: int | None = None
    transporter_column: str | None = None
    driver_column: str | None = None
    driver_identifier_kind: str | None = None
    rows_detected: int = Field(default=0, ge=0)
    candidate_sheets: list[str] = Field(default_factory=list)
    transporter_candidates: list[str] = Field(default_factory=list)
    driver_candidates: list[str] = Field(default_factory=list)


class IdentitySourceCoverage(BaseModel):
    quality_transporters: int = Field(default=0, ge=0)
    source_transporters: int = Field(default=0, ge=0)
    exact_matches: int = Field(default=0, ge=0)
    suggestions: int = Field(default=0, ge=0)
    unresolved: int = Field(default=0, ge=0)
    conflicts: int = Field(default=0, ge=0)
    already_verified: int = Field(default=0, ge=0)
    source_only: int = Field(default=0, ge=0)


class IdentitySourcePreviewRow(BaseModel):
    transporter_external_id: str
    source_driver_value: str | None = None
    proposed_workforce_member_id: int | None = None
    proposed_display_name: str | None = None
    confidence: IdentityConfidenceClass
    evidence_source: str
    status: IdentityEvidenceStatus
    reason: str
    source_sheet: str | None = None
    source_row: int | None = None


class IdentitySourcePreview(BaseModel):
    valid: bool
    schema_status: Literal["READY", "AMBIGUOUS_SCHEMA", "NO_VALID_SCHEMA"]
    scorecard_id: str
    preview_token: str | None = None
    source: IdentitySourceMetadata
    coverage: IdentitySourceCoverage = Field(default_factory=IdentitySourceCoverage)
    default_bucket: Literal["exact", "suggested", "unresolved", "conflict"] = "suggested"
    rows: list[IdentitySourcePreviewRow] = Field(default_factory=list)


class ExactIdentityApplyResult(BaseModel):
    scorecard_id: str
    applied: int = Field(default=0, ge=0)
    already_verified: int = Field(default=0, ge=0)
    mappings: list[str] = Field(default_factory=list)

