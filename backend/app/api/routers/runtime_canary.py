from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import ValidationError

from app.api.dependencies.runtime_canary import get_runtime_canary
from app.domain.runtime_canary import RuntimeCanaryScope
from app.runtime.canary import RuntimeCanaryRuntime
from app.schemas.runtime_canary_schema import RuntimeCanaryResponse


router = APIRouter(prefix="/api/runtime/canary", tags=["runtime-canary"])


@router.get("", response_model=RuntimeCanaryResponse)
def get_runtime_canary_report(
    organization_id: Annotated[str, Query(min_length=1, max_length=120)],
    operational_unit_id: Annotated[
        str,
        Query(min_length=1, max_length=120),
    ],
    planning_date: date,
    timezone: Annotated[str, Query(min_length=1, max_length=120)],
    publication_id: Annotated[str, Query(min_length=1, max_length=120)],
    publication_version: Annotated[int, Query(ge=1)],
    runtime: RuntimeCanaryRuntime = Depends(get_runtime_canary),
) -> RuntimeCanaryResponse:
    try:
        scope = RuntimeCanaryScope(
            organization_id=organization_id,
            operational_unit_id=operational_unit_id,
            planning_date=planning_date,
            timezone=timezone,
        )
    except ValidationError as exc:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "INVALID_RUNTIME_CANARY_SCOPE",
                "message": "Scope Runtime Canary non valido.",
            },
        ) from exc
    result = runtime.current(
        scope=scope,
        publication_id=publication_id,
        publication_version=publication_version,
    )
    return RuntimeCanaryResponse.model_validate(
        result.model_dump(mode="json")
    )
