from pydantic import BaseModel


class PlanningExportRow(BaseModel):
    operation_date: str
    station: str
    route_id: str
    cycle_or_wave: str | None = None
    driver_name: str | None = None
    plate: str | None = None
    assignment_status: str
    assignment_source: str
    manual_override: bool
    warnings: str
    notes: str | None = None
