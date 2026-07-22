from datetime import UTC, date, datetime
from typing import Annotated, Callable, TypeVar

from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.dependencies.planning_publication import (
    get_planning_publication_runtime,
)
from app.domain.core_language import OperationalUnit
from app.domain.planning_publication import (
    PlanningPublicationAlreadyExistsError,
    PlanningPublicationError,
    PlanningPublicationHistory,
    PlanningPublicationReport,
)
from app.runtime.planning_publication import PlanningPublicationRuntime
from app.schemas.planning_publication_schema import (
    PlanningPublicationRequest,
)


router = APIRouter(
    prefix="/api/planning/publication",
    tags=["planning-publication"],
)
Result = TypeVar("Result")


def _execute(operation: Callable[[], Result]) -> Result:
    try:
        return operation()
    except PlanningPublicationAlreadyExistsError as exc:
        raise HTTPException(
            status_code=409,
            detail={"code": exc.code, "message": str(exc)},
        ) from exc
    except PlanningPublicationError as exc:
        raise HTTPException(
            status_code=400,
            detail={"code": exc.code, "message": str(exc)},
        ) from exc


def _unit(identifier: str, name: str | None = None) -> OperationalUnit:
    return OperationalUnit(external_identifier=identifier, name=name)


@router.get("/current", response_model=PlanningPublicationReport)
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
    runtime: PlanningPublicationRuntime = Depends(
        get_planning_publication_runtime
    ),
) -> PlanningPublicationReport:
    evaluated_at = datetime.now(UTC)
    return runtime.current(
        organization_id=organization_id,
        operational_unit=_unit(operational_unit_id),
        planning_date=planning_date or evaluated_at.date(),
        evaluated_at=evaluated_at,
    )


@router.post("/validate", response_model=PlanningPublicationReport)
def validate(
    request: PlanningPublicationRequest,
    runtime: PlanningPublicationRuntime = Depends(
        get_planning_publication_runtime
    ),
) -> PlanningPublicationReport:
    return runtime.validate(
        organization_id=request.organization_id,
        operational_unit=_unit(
            request.operational_unit_id,
            request.operational_unit_name,
        ),
        planning_date=request.planning_date,
        confirmation_id=request.confirmation_id,
        confirmation_version=request.confirmation_version,
        confirmation_fingerprint=request.confirmation_fingerprint,
        evaluated_at=datetime.now(UTC),
    )


@router.post("/publish", response_model=PlanningPublicationReport)
def publish(
    request: PlanningPublicationRequest,
    runtime: PlanningPublicationRuntime = Depends(
        get_planning_publication_runtime
    ),
) -> PlanningPublicationReport:
    return _execute(
        lambda: runtime.publish(
            organization_id=request.organization_id,
            operational_unit=_unit(
                request.operational_unit_id,
                request.operational_unit_name,
            ),
            planning_date=request.planning_date,
            confirmation_id=request.confirmation_id,
            confirmation_version=request.confirmation_version,
            confirmation_fingerprint=request.confirmation_fingerprint,
            evaluated_at=datetime.now(UTC),
        )
    )


@router.get("/history", response_model=PlanningPublicationHistory)
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
    runtime: PlanningPublicationRuntime = Depends(
        get_planning_publication_runtime
    ),
) -> PlanningPublicationHistory:
    evaluated_at = datetime.now(UTC)
    return runtime.history(
        organization_id=organization_id,
        operational_unit=_unit(operational_unit_id),
        planning_date=planning_date or evaluated_at.date(),
    )
