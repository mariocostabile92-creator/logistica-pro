from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import ValidationError

from app.api.dependencies.runtime_authority import get_authority_runtime
from app.domain.runtime_authority import AuthorityScope
from app.runtime.authority import AuthorityRuntimeService
from app.schemas.runtime_authority_schema import AuthorityRuntimeResponse


router = APIRouter(
    prefix="/api/runtime/authority",
    tags=["runtime-authority"],
)


@router.get("", response_model=AuthorityRuntimeResponse)
def get_authority(
    organization_id: Annotated[
        str,
        Query(min_length=1, max_length=120),
    ],
    operational_unit_id: Annotated[
        str,
        Query(min_length=1, max_length=120),
    ],
    planning_date: date,
    timezone: Annotated[
        str,
        Query(min_length=1, max_length=120),
    ],
    runtime: AuthorityRuntimeService = Depends(get_authority_runtime),
) -> AuthorityRuntimeResponse:
    try:
        scope = AuthorityScope(
            organization_id=organization_id,
            operational_unit_id=operational_unit_id,
            planning_date=planning_date,
            timezone=timezone,
        )
    except ValidationError as exc:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "INVALID_AUTHORITY_SCOPE",
                "message": "Scope Authority non valido.",
            },
        ) from exc
    return AuthorityRuntimeResponse.model_validate(
        runtime.report(scope).model_dump(mode="json")
    )
