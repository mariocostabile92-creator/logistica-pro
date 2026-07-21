from enum import Enum

from pydantic import BaseModel, Field


class FleetInterpretationStatus(str, Enum):
    RECOGNIZED = "RECOGNIZED"
    INFERRED = "INFERRED"
    NEEDS_CONFIRMATION = "NEEDS_CONFIRMATION"
    IGNORED = "IGNORED"
    SENSITIVE = "SENSITIVE"


class FleetSyncAction(str, Enum):
    NEW_ASSET = "NEW_ASSET"
    UPDATE_EXISTING = "UPDATE_EXISTING"
    NO_CHANGE = "NO_CHANGE"
    POSSIBLE_DUPLICATE = "POSSIBLE_DUPLICATE"
    CONFLICT = "CONFLICT"
    INVALID_ROW = "INVALID_ROW"


class SensitiveField(BaseModel):
    column: str
    classification: FleetInterpretationStatus = FleetInterpretationStatus.SENSITIVE
    reason: str = "Campo sensibile rilevato: escluso dall'import automatico."


class FleetSyncItem(BaseModel):
    row_id: int
    excel_row: int
    external_identifier: str | None = None
    plate: str | None = None
    current: dict[str, object] | None = None
    proposed: dict[str, object] = Field(default_factory=dict)
    difference: dict[str, dict[str, object]] = Field(default_factory=dict)
    confidence: float = Field(ge=0, le=1)
    action: FleetSyncAction
    interpretation: FleetInterpretationStatus
    reason: str
    selected_by_default: bool = False
    sensitive_fields: list[SensitiveField] = Field(default_factory=list)


class FleetSyncSummary(BaseModel):
    total_rows: int = 0
    new_assets: int = 0
    updated_assets: int = 0
    unchanged_assets: int = 0
    unavailable_assets: int = 0
    maintenance_assets: int = 0
    reserve_assets: int = 0
    possible_duplicates: int = 0
    conflicts: int = 0
    invalid_rows: int = 0
    sensitive_fields_excluded: int = 0


class FleetSyncPreview(BaseModel):
    workbook_type: str = "FLEET_REGISTRY"
    fingerprint: str
    original_filename: str
    profiled_sheets: int
    selected_sheet: str
    selected_header_row: int
    source_rows: int
    mappings: list[dict[str, object]]
    summary: FleetSyncSummary
    items: list[FleetSyncItem]


class FleetSyncResult(BaseModel):
    fingerprint: str
    import_id: int
    idempotent: bool = False
    created_assets: int = 0
    updated_assets: int = 0
    unchanged_assets: int = 0
    events_created: int = 0
    documents_created: int = 0
    selected_rows: int = 0


class FleetBriefingSnapshot(BaseModel):
    total_assets: int = 0
    unavailable_assets: int = 0
    maintenance_assets: int = 0
    reserve_assets: int = 0
    documents_attention: int = 0
    recent_updates: int = 0
    unresolved_conflicts: int = 0
