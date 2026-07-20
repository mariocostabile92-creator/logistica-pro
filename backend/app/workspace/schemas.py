from pydantic import BaseModel, Field

from app.workspace.models import WorkspaceAction, WorkspaceState


class WorkspaceImportReference(BaseModel):
    import_id: int
    original_filename: str
    imported_at: str
    rows_imported: int = Field(ge=0)


class WorkspaceStatusResponse(BaseModel):
    workspace_state: WorkspaceState
    is_demo: bool
    demo_enabled: bool
    mixed_data_detected: bool = False
    latest_planning_import: WorkspaceImportReference | None = None
    latest_fleet_import: WorkspaceImportReference | None = None
    task_count: int = Field(default=0, ge=0)
    asset_count: int = Field(default=0, ge=0)
    planning_count: int = Field(default=0, ge=0)
    briefing_count: int = Field(default=0, ge=0)
    last_operational_update: str | None = None
    can_reset: bool
    available_actions: list[WorkspaceAction] = Field(default_factory=list)


class WorkspaceRemovedCounts(BaseModel):
    daily_briefings: int = 0
    planning_events: int = 0
    planning_versions: int = 0
    assignments: int = 0
    plannings: int = 0
    operation_snapshots: int = 0
    analyses: int = 0
    fleet_asset_documents: int = 0
    fleet_asset_events: int = 0
    fleet_assets: int = 0
    imports: int = 0
    demo_workspaces: int = 0


class WorkspaceResetResponse(BaseModel):
    reset_id: str
    workspace_state: WorkspaceState
    is_demo: bool = False
    idempotent: bool
    message_code: str
    removed_counts: WorkspaceRemovedCounts
    completed_at: str
