from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import ValidationError

from app.api.dependencies.planning_runtime_output import (
    get_planning_runtime_output,
)
from app.domain.planning_runtime import PlanningRuntimeScope
from app.runtime.planning_output import PlanningRuntimeOutputRuntime
from app.schemas.planning_runtime_output_schema import (
    PlanningRuntimeOutputResponse,
)


router = APIRouter(prefix="/api/runtime/output", tags=["runtime-output"])


@router.get("", response_model=PlanningRuntimeOutputResponse)
def get_runtime_output(
    organization_id: Annotated[str, Query(min_length=1, max_length=120)],
    operational_unit_id: Annotated[
        str,
        Query(min_length=1, max_length=120),
    ],
    planning_date: date,
    timezone: Annotated[str, Query(min_length=1, max_length=120)],
    publication_id: Annotated[str, Query(min_length=1, max_length=120)],
    publication_version: Annotated[int, Query(ge=1)],
    runtime: PlanningRuntimeOutputRuntime = Depends(
        get_planning_runtime_output
    ),
) -> PlanningRuntimeOutputResponse:
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
                "code": "INVALID_PLANNING_RUNTIME_SCOPE",
                "message": "Scope Planning Runtime non valido.",
            },
        ) from exc

    result = runtime.current(
        scope=scope,
        publication_id=publication_id,
        publication_version=publication_version,
    )
    return PlanningRuntimeOutputResponse.model_validate(
        result.model_dump(mode="json")
    )
