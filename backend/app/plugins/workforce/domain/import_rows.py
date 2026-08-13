from pydantic import BaseModel, Field


class WorkforceImportRow(BaseModel):
    id: int
    organization_id: str
    workforce_import_id: int
    source_filename: str
    imported_at: str
    source_sheet: str
    source_row_number: int = Field(gt=0)
    source_reference: str
    source_record_key: str
    row_kind: str
    source_external_identifier: str | None = None
    driver_display_name: str | None = None
    transporter_id: str | None = None
    station: str | None = None
    operational_date: str | None = None
    status_code: str | None = None
    availability: bool | None = None
    shift_code: str | None = None
    operational_activity: str | None = None
    start_time: str | None = None
    end_time: str | None = None
    notes: str | None = None
    employment_type: str | None = None
    operational_cycle: str | None = None
    contract_start: str | None = None
    contract_end: str | None = None
    weekly_hours: float | None = None
    resolved_workforce_member_id: int | None = None
    raw_payload: dict[str, object] = Field(default_factory=dict)
