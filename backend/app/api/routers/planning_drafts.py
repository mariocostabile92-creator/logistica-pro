from datetime import UTC, date, datetime
from typing import Annotated, Callable, TypeVar

from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.dependencies.planning_drafts import get_planning_draft_runtime
from app.domain.core_language import OperationalUnit
from app.domain.planning_drafts import (
    PlanningDraftAlreadyExistsError,
    PlanningDraftError,
    PlanningDraftHistory,
    PlanningDraftInvalidStateError,
    PlanningDraftMetadata,
    PlanningDraftNotFoundError,
    PlanningDraftSnapshotNotFoundError,
    PlanningDraftVersionConflictError,
    PlanningDraftWorkspace,
)
from app.runtime.planning_drafts import PlanningDraftRuntime
from app.schemas.planning_draft_schema import (
    PlanningDraftCreateRequest,
    PlanningDraftMetadataUpdateRequest,
    PlanningDraftRestoreRequest,
    PlanningDraftVersionRequest,
)


router = APIRouter(prefix="/api/planning/drafts", tags=["planning-drafts"])
Result = TypeVar("Result")


def _execute(operation: Callable[[], Result]) -> Result:
    try:
        return operation()
    except PlanningDraftNotFoundError as exc:
        raise HTTPException(
            status_code=404,
            detail={"code": exc.code, "message": str(exc)},
        ) from exc
    except PlanningDraftSnapshotNotFoundError as exc:
        raise HTTPException(
            status_code=404,
            detail={"code": exc.code, "message": str(exc)},
        ) from exc
    except (
        PlanningDraftAlreadyExistsError,
        PlanningDraftInvalidStateError,
        PlanningDraftVersionConflictError,
    ) as exc:
        raise HTTPException(
            status_code=409,
            detail={"code": exc.code, "message": str(exc)},
        ) from exc
    except PlanningDraftError as exc:
        raise HTTPException(
            status_code=400,
            detail={"code": exc.code, "message": str(exc)},
        ) from exc


@router.get("/current", response_model=PlanningDraftWorkspace)
def current(
    organization_id: Annotated[
        str,
        Query(min_length=1, max_length=120),
    ] = "default",
    operational_unit_id: Annotated[
        str,
        Query(min_length=1, max_length=120),
    ] = "default",
    planning_date: date | None = Query(default=None),
    runtime: PlanningDraftRuntime = Depends(get_planning_draft_runtime),
) -> PlanningDraftWorkspace:
    return runtime.current(
        organization_id=organization_id,
        operational_unit=OperationalUnit(
            external_identifier=operational_unit_id
        ),
        planning_date=planning_date or datetime.now(UTC).date(),
    )


@router.post("", response_model=PlanningDraftWorkspace, status_code=201)
def create(
    request: PlanningDraftCreateRequest,
    runtime: PlanningDraftRuntime = Depends(get_planning_draft_runtime),
) -> PlanningDraftWorkspace:
    return _execute(
        lambda: runtime.create(
            organization_id=request.organization_id,
            operational_unit=OperationalUnit(
                external_identifier=request.operational_unit_id,
                name=request.operational_unit_name,
            ),
            planning_date=request.planning_date,
            metadata=PlanningDraftMetadata(
                name=request.name,
                note=request.note,
            ),
        )
    )


@router.patch("/{draft_id}/metadata", response_model=PlanningDraftWorkspace)
def update_metadata(
    draft_id: str,
    request: PlanningDraftMetadataUpdateRequest,
    runtime: PlanningDraftRuntime = Depends(get_planning_draft_runtime),
) -> PlanningDraftWorkspace:
    changes = request.model_dump(
        include={"name", "note"},
        exclude_unset=True,
    )
    return _execute(
        lambda: runtime.update_metadata(
            draft_id=draft_id,
            expected_version=request.expected_version,
            changes=changes,
        )
    )


@router.post("/{draft_id}/save", response_model=PlanningDraftWorkspace)
def save(
    draft_id: str,
    request: PlanningDraftVersionRequest,
    runtime: PlanningDraftRuntime = Depends(get_planning_draft_runtime),
) -> PlanningDraftWorkspace:
    return _execute(
        lambda: runtime.save(
            draft_id=draft_id,
            expected_version=request.expected_version,
        )
    )


@router.post("/{draft_id}/restore", response_model=PlanningDraftWorkspace)
def restore(
    draft_id: str,
    request: PlanningDraftRestoreRequest,
    runtime: PlanningDraftRuntime = Depends(get_planning_draft_runtime),
) -> PlanningDraftWorkspace:
    return _execute(
        lambda: runtime.restore(
            draft_id=draft_id,
            expected_version=request.expected_version,
            target_version=request.target_version,
        )
    )


@router.delete("/{draft_id}", response_model=PlanningDraftWorkspace)
def delete(
    draft_id: str,
    expected_version: Annotated[int, Query(ge=1)],
    runtime: PlanningDraftRuntime = Depends(get_planning_draft_runtime),
) -> PlanningDraftWorkspace:
    return _execute(
        lambda: runtime.delete(
            draft_id=draft_id,
            expected_version=expected_version,
        )
    )


@router.get("/{draft_id}/history", response_model=PlanningDraftHistory)
def history(
    draft_id: str,
    runtime: PlanningDraftRuntime = Depends(get_planning_draft_runtime),
) -> PlanningDraftHistory:
    return _execute(lambda: runtime.history(draft_id))
