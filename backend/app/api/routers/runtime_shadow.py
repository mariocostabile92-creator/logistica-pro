from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import ValidationError

from app.api.dependencies.runtime_shadow import get_runtime_shadow
from app.domain.runtime_shadow import RuntimeShadowScope
from app.runtime.shadow import RuntimeShadowRuntime
from app.schemas.runtime_shadow_schema import RuntimeShadowResponse


router = APIRouter(prefix="/api/runtime/shadow", tags=["runtime-shadow"])


@router.get("", response_model=RuntimeShadowResponse)
def get_shadow_result(
    organization_id: Annotated[str, Query(min_length=1, max_length=120)],
    operational_unit_id: Annotated[
        str,
        Query(min_length=1, max_length=120),
    ],
    planning_date: date,
    timezone: Annotated[str, Query(min_length=1, max_length=120)],
    publication_version: Annotated[int, Query(ge=1)],
    runtime: RuntimeShadowRuntime = Depends(get_runtime_shadow),
) -> RuntimeShadowResponse:
    try:
        scope = RuntimeShadowScope(
            organization_id=organization_id,
            operational_unit_id=operational_unit_id,
            planning_date=planning_date,
            timezone=timezone,
        )
    except ValidationError as exc:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "INVALID_RUNTIME_SHADOW_SCOPE",
                "message": "Scope Runtime Shadow non valido.",
            },
        ) from exc

    return RuntimeShadowResponse.model_validate(
        runtime.current(
            scope=scope,
            publication_version=publication_version,
        ).model_dump(mode="json")
    )
