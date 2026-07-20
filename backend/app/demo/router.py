from fastapi import APIRouter, HTTPException

from app.demo.schemas import (
    DemoLoadResponse,
    DemoResetResponse,
    DemoStatusResponse,
)
from app.demo.service import (
    DemoWorkspaceLoadError,
    DemoWorkspaceResetError,
    get_demo_status,
    load_demo_workspace,
    reset_demo_workspace,
)
from app.demo.settings import demo_workspace_enabled


router = APIRouter(prefix="/api/demo/v1", tags=["private-beta-demo-v1"])


def _require_demo_enabled() -> None:
    if not demo_workspace_enabled():
        raise HTTPException(status_code=404, detail="Risorsa non trovata.")


@router.get("/status", response_model=DemoStatusResponse)
def status() -> DemoStatusResponse:
    _require_demo_enabled()
    return get_demo_status()


@router.post("/load", response_model=DemoLoadResponse)
def load() -> DemoLoadResponse:
    _require_demo_enabled()
    try:
        return load_demo_workspace()
    except DemoWorkspaceLoadError as exc:
        raise HTTPException(
            status_code=500,
            detail={
                "code": "DEMO_LOAD_FAILED",
                "message": str(exc),
            },
        ) from exc


@router.post("/reset", response_model=DemoResetResponse)
def reset() -> DemoResetResponse:
    _require_demo_enabled()
    try:
        return reset_demo_workspace()
    except DemoWorkspaceResetError as exc:
        raise HTTPException(
            status_code=500,
            detail={
                "code": "DEMO_RESET_FAILED",
                "message": str(exc),
            },
        ) from exc

