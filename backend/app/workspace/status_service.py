from app.demo.settings import demo_workspace_enabled
from app.workspace import repository
from app.workspace.models import WorkspaceAction, WorkspaceState
from app.workspace.schemas import (
    WorkspaceImportReference,
    WorkspaceStatusResponse,
)


class DemoWorkspaceResetRequiredError(RuntimeError):
    pass


class ProductionWorkspaceNotEmptyError(RuntimeError):
    pass


def _state_from_inventory(inventory: dict[str, object]) -> WorkspaceState:
    if inventory["active_demo"] and not inventory["non_demo_data"]:
        return WorkspaceState.DEMO
    if inventory["has_operational_data"]:
        return WorkspaceState.PRODUCTION
    return WorkspaceState.EMPTY


def _available_actions(
    state: WorkspaceState,
    *,
    demo_enabled: bool,
) -> list[WorkspaceAction]:
    if state == WorkspaceState.EMPTY:
        actions = [WorkspaceAction.IMPORT_DATA]
        if demo_enabled:
            actions.append(WorkspaceAction.LOAD_DEMO)
        return actions
    if state == WorkspaceState.DEMO:
        return [
            WorkspaceAction.NEW_OPERATIONAL_DAY,
            WorkspaceAction.RESET_WORKSPACE,
            WorkspaceAction.IMPORT_REAL_DATA,
        ]
    return [
        WorkspaceAction.IMPORT_NEW_DATA,
        WorkspaceAction.NEW_OPERATIONAL_DAY,
        WorkspaceAction.RESET_WORKSPACE,
    ]


def get_workspace_status() -> WorkspaceStatusResponse:
    inventory = repository.read_inventory()
    state = _state_from_inventory(inventory)
    enabled = demo_workspace_enabled()
    return WorkspaceStatusResponse(
        workspace_state=state,
        is_demo=state == WorkspaceState.DEMO,
        demo_enabled=enabled,
        mixed_data_detected=bool(
            inventory["active_demo"] and inventory["non_demo_data"]
        ),
        latest_planning_import=(
            WorkspaceImportReference.model_validate(
                inventory["latest_planning_import"]
            )
            if inventory["latest_planning_import"]
            else None
        ),
        latest_fleet_import=(
            WorkspaceImportReference.model_validate(
                inventory["latest_fleet_import"]
            )
            if inventory["latest_fleet_import"]
            else None
        ),
        task_count=int(inventory["task_count"]),
        asset_count=int(inventory["asset_count"]),
        planning_count=int(inventory["planning_count"]),
        briefing_count=int(inventory["briefing_count"]),
        last_operational_update=inventory["last_operational_update"],
        can_reset=state != WorkspaceState.EMPTY,
        available_actions=_available_actions(
            state,
            demo_enabled=enabled,
        ),
    )


def ensure_real_data_write_allowed() -> None:
    if get_workspace_status().workspace_state == WorkspaceState.DEMO:
        raise DemoWorkspaceResetRequiredError(
            "Rimuovi il Demo Workspace prima di aggiungere dati reali."
        )


def ensure_demo_load_allowed() -> None:
    status = get_workspace_status()
    if status.workspace_state == WorkspaceState.PRODUCTION:
        raise ProductionWorkspaceNotEmptyError(
            "Ripristina il workspace prima di caricare i dati demo."
        )
