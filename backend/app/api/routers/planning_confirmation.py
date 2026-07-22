from datetime import UTC, date, datetime
from typing import Annotated, Callable, TypeVar

from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.dependencies.planning_confirmation import (
    get_planning_confirmation_runtime,
)
from app.domain.core_language import OperationalUnit
from app.domain.planning_confirmation import (
    PlanningConfirmationAlreadyExistsError,
    PlanningConfirmationError,
    PlanningConfirmationHistory,
    PlanningConfirmationReport,
)
from app.runtime.planning_confirmation import PlanningConfirmationRuntime
from app.schemas.planning_confirmation_schema import (
    PlanningConfirmationRequest,
)


router = APIRouter(
    prefix="/api/planning/confirmation",
    tags=["planning-confirmation"],
)
Result = TypeVar("Result")


def _execute(operation: Callable[[], Result]) -> Result:
    try:
        return operation()
    except PlanningConfirmationAlreadyExistsError as exc:
        raise HTTPException(
            status_code=409,
            detail={"code": exc.code, "message": str(exc)},
        ) from exc
    except PlanningConfirmationError as exc:
        raise HTTPException(
            status_code=400,
            detail={"code": exc.code, "message": str(exc)},
        ) from exc


def _unit(identifier: str, name: str | None = None) -> OperationalUnit:
    return OperationalUnit(external_identifier=identifier, name=name)


@router.get("/current", response_model=PlanningConfirmationReport)
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
    runtime: PlanningConfirmationRuntime = Depends(
        get_planning_confirmation_runtime
    ),
) -> PlanningConfirmationReport:
    evaluated_at = datetime.now(UTC)
    return runtime.current(
        organization_id=organization_id,
        operational_unit=_unit(operational_unit_id),
        planning_date=planning_date or evaluated_at.date(),
        evaluated_at=evaluated_at,
    )


@router.post("/validate", response_model=PlanningConfirmationReport)
def validate(
    request: PlanningConfirmationRequest,
    runtime: PlanningConfirmationRuntime = Depends(
        get_planning_confirmation_runtime
    ),
) -> PlanningConfirmationReport:
    return runtime.validate(
        organization_id=request.organization_id,
        operational_unit=_unit(
            request.operational_unit_id,
            request.operational_unit_name,
        ),
        planning_date=request.planning_date,
        draft_id=request.draft_id,
        draft_version=request.draft_version,
        evaluated_at=datetime.now(UTC),
    )


@router.post("/confirm", response_model=PlanningConfirmationReport)
def confirm(
    request: PlanningConfirmationRequest,
    runtime: PlanningConfirmationRuntime = Depends(
        get_planning_confirmation_runtime
    ),
) -> PlanningConfirmationReport:
    return _execute(
        lambda: runtime.confirm(
            organization_id=request.organization_id,
            operational_unit=_unit(
                request.operational_unit_id,
                request.operational_unit_name,
            ),
            planning_date=request.planning_date,
            draft_id=request.draft_id,
            draft_version=request.draft_version,
            evaluated_at=datetime.now(UTC),
        )
    )


@router.get("/history", response_model=PlanningConfirmationHistory)
def history(
    organization_id: Annotated[
        str,
        Query(min_length=1, max_length=120),
    ] = "default",
    operational_unit_id: Annotated[
        str,
        Query(min_length=1, max_length=120),
    ] = "default",
    planning_date: date | None = Query(default=None),
    runtime: PlanningConfirmationRuntime = Depends(
        get_planning_confirmation_runtime
    ),
) -> PlanningConfirmationHistory:
    evaluated_at = datetime.now(UTC)
    return runtime.history(
        organization_id=organization_id,
        operational_unit=_unit(operational_unit_id),
        planning_date=planning_date or evaluated_at.date(),
    )
