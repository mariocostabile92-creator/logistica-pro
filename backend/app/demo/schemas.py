from enum import Enum

from pydantic import BaseModel, Field


class DemoWorkspaceState(str, Enum):
    NO_DEMO = "no_demo"
    LOADING = "loading"
    PARTIAL = "partial"
    FAILED = "failed"
    READY = "ready"
    RESET = "reset"


class DemoDatasetCounts(BaseModel):
    tasks: int = 0
    human_resources: int = 0
    absent_human_resources: int = 0
    assets: int = 0
    unavailable_assets: int = 0
    reserve_assets: int = 0
    time_windows: int = 0
    warnings: int = 0
    alternatives: int = 0
    events: int = 0


class DemoWorkspaceSummary(BaseModel):
    demo_workspace_id: str
    dataset_version: str
    is_demo: bool = True
    status: DemoWorkspaceState
    organization: str
    operational_unit: str
    operation_date: str
    created_at: str
    created_by: str
    planning_id: int | None = None
    planning_status: str | None = None
    readiness_status: str | None = None
    warning_codes: list[str] = Field(default_factory=list)
    counts: DemoDatasetCounts = Field(default_factory=DemoDatasetCounts)


class DemoStatusResponse(BaseModel):
    enabled: bool = True
    present: bool
    status: DemoWorkspaceState
    summary: DemoWorkspaceSummary | None = None


class DemoLoadResponse(BaseModel):
    created: bool
    idempotent: bool
    summary: DemoWorkspaceSummary


class DemoRemovedCounts(BaseModel):
    imports: int = 0
    plannings: int = 0
    operation_snapshots: int = 0
    fleet_assets: int = 0


class DemoResetResponse(BaseModel):
    demo_workspace_id: str
    status: DemoWorkspaceState = DemoWorkspaceState.RESET
    idempotent: bool
    removed: DemoRemovedCounts

