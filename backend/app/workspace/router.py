from fastapi import APIRouter, HTTPException

from app.workspace.reset_service import (
    WorkspaceResetFailedError,
    WorkspaceResetInProgressError,
    reset_workspace,
)
from app.workspace.schemas import (
    WorkspaceResetResponse,
    WorkspaceStatusResponse,
)
from app.workspace.status_service import get_workspace_status


router = APIRouter(
    prefix="/api/workspace/v1",
    tags=["workspace-lifecycle-v1"],
)


@router.get("/status", response_model=WorkspaceStatusResponse)
def status() -> WorkspaceStatusResponse:
    return get_workspace_status()


@router.post("/reset", response_model=WorkspaceResetResponse)
def reset() -> WorkspaceResetResponse:
    try:
        return reset_workspace()
    except WorkspaceResetInProgressError as exc:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "WORKSPACE_RESET_IN_PROGRESS",
                "message": str(exc),
            },
        ) from exc
    except WorkspaceResetFailedError as exc:
        raise HTTPException(
            status_code=500,
            detail={
                "code": "WORKSPACE_RESET_FAILED",
                "message": str(exc),
            },
        ) from exc
