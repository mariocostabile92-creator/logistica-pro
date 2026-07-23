from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.api.dependencies.legacy_retirement import get_legacy_retirement
from app.domain.legacy_retirement import LegacyRetirementScope
from app.runtime.legacy_retirement import LegacyRetirementRuntime
from app.schemas.legacy_retirement_schema import (
    LegacyRetirementResponse,
)


router = APIRouter(
    prefix="/api/runtime/legacy-retirement",
    tags=["legacy-retirement"],
)


@router.get(
    "",
    response_model=LegacyRetirementResponse,
    response_model_exclude_none=True,
)
def get_legacy_retirement_report(
    organization_id: Annotated[str, Query(min_length=1, max_length=120)],
    runtime: LegacyRetirementRuntime = Depends(get_legacy_retirement),
) -> LegacyRetirementResponse:
    scope = LegacyRetirementScope(organization_id=organization_id)
    report = runtime.current(scope=scope)
    return LegacyRetirementResponse(report=report)
