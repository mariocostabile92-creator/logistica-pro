from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import ValidationError

from app.api.dependencies.runtime_primary import get_runtime_primary
from app.domain.planning_runtime import PlanningRuntimeScope
from app.runtime.primary import RuntimePrimaryRuntime
from app.schemas.runtime_primary_schema import RuntimePrimaryResponse


router = APIRouter(
    prefix="/api/runtime/primary",
    tags=["runtime-primary"],
)


@router.get("", response_model=RuntimePrimaryResponse)
def get_runtime_primary_report(
    organization_id: Annotated[str, Query(min_length=1, max_length=120)],
    operational_unit_id: Annotated[
        str,
        Query(min_length=1, max_length=120),
    ],
    planning_date: date,
    timezone: Annotated[str, Query(min_length=1, max_length=120)],
    publication_id: Annotated[str, Query(min_length=1, max_length=120)],
    publication_version: Annotated[int, Query(ge=1)],
    runtime: RuntimePrimaryRuntime = Depends(get_runtime_primary),
) -> RuntimePrimaryResponse:
    try:
        scope = PlanningRuntimeScope(
            organization_id=organization_id,
            operational_unit_id=operational_unit_id,
            planning_date=planning_date,
            timezone=timezone,
        )
    except ValidationError as exc:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "INVALID_RUNTIME_PRIMARY_SCOPE",
                "message": "Scope Runtime Primary non valido.",
            },
        ) from exc
    report = runtime.current(
        scope=scope,
        publication_id=publication_id,
        publication_version=publication_version,
    )
    return RuntimePrimaryResponse(report=report)
