from datetime import UTC, date, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.api.dependencies.planning_conflicts import (
    get_planning_conflict_service,
)
from app.domain.core_language import OperationalUnit
from app.domain.planning_conflicts import PlanningConflictResult
from app.runtime.planning_conflicts import PlanningConflictService


router = APIRouter(prefix="/api/planning", tags=["planning"])


@router.get("/conflicts", response_model=PlanningConflictResult)
def conflicts(
    organization_id: Annotated[
        str,
        Query(min_length=1, max_length=120),
    ] = "default",
    operational_unit_id: Annotated[
        str,
        Query(min_length=1, max_length=120),
    ] = "default",
    operation_date: date | None = Query(default=None),
    service: PlanningConflictService = Depends(get_planning_conflict_service),
) -> PlanningConflictResult:
    evaluated_at = datetime.now(UTC)
    return service.review(
        organization_id=organization_id,
        operational_unit=OperationalUnit(
            external_identifier=operational_unit_id
        ),
        operation_date=operation_date or evaluated_at.date(),
        evaluated_at=evaluated_at,
    )
