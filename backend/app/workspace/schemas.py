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
    workforce_member_count: int = Field(default=0, ge=0)
    planning_count: int = Field(default=0, ge=0)
    briefing_count: int = Field(default=0, ge=0)
    last_operational_update: str | None = None
    can_reset: bool
    available_actions: list[WorkspaceAction] = Field(default_factory=list)


class WorkspaceRemovedCounts(BaseModel):
    attachment_events: int = 0
    attachments: int = 0
    workforce_external_identity_events: int = 0
    workforce_external_identities: int = 0
    dsp_quality_transporter_observations: int = 0
    dsp_quality_focus_areas: int = 0
    dsp_quality_working_hour_exceptions: int = 0
    dsp_quality_section_standings: int = 0
    dsp_quality_metric_observations: int = 0
    dsp_quality_transporter_rows: int = 0
    dsp_quality_scorecard_versions: int = 0
    dsp_quality_scorecards: int = 0
    runtime_execution_attempts: int = 0
    runtime_execution_intents: int = 0
    runtime_authority_decisions: int = 0
    planning_publications: int = 0
    planning_confirmations: int = 0
    planning_convocations: int = 0
    planning_draft_changes: int = 0
    planning_draft_versions: int = 0
    planning_drafts: int = 0
    daily_briefings: int = 0
    planning_events: int = 0
    planning_versions: int = 0
    assignments: int = 0
    plannings: int = 0
    operation_snapshots: int = 0
    analyses: int = 0
    workforce_import_rows: int = 0
    driver_shift_planning_sources: int = 0
    driver_shift_planning_resolutions: int = 0
    driver_shift_planning_published_rows: int = 0
    driver_shift_distributions: int = 0
    driver_shift_distribution_recipients: int = 0
    driver_shift_plannings: int = 0
    workforce_changes: int = 0
    workforce_day_statuses: int = 0
    workforce_requirements: int = 0
    workforce_members: int = 0
    workforce_imports: int = 0
    fleet_document_events: int = 0
    fleet_maintenance_events: int = 0
    fleet_rentals: int = 0
    fleet_franchise_cases: int = 0
    fleet_maintenances: int = 0
    damage_case_events: int = 0
    damage_cases: int = 0
    fleet_insurance_policies: int = 0
    fleet_vehicle_documents: int = 0
    movement_media: int = 0
    movement_equipment: int = 0
    asset_movements: int = 0
    journal_sessions: int = 0
    journal_shared_access: int = 0
    fleet_asset_profiles: int = 0
    fleet_asset_documents: int = 0
    fleet_sync_event_fingerprints: int = 0
    fleet_asset_events: int = 0
    fleet_sync_runs: int = 0
    fleet_asset_metadata: int = 0
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
