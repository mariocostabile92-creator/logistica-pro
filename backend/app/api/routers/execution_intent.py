from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import ValidationError

from app.api.dependencies.execution_intent import (
    get_execution_intent_runtime,
)
from app.domain.execution_intent import (
    ExecutionIntentMode,
    ExecutionIntentScope,
)
from app.runtime.execution_intent import ExecutionIntentRuntime
from app.schemas.execution_intent_schema import (
    ExecutionIntentRuntimeResponse,
)


router = APIRouter(
    prefix="/api/runtime/execution-intent",
    tags=["execution-intent"],
)


@router.get("", response_model=ExecutionIntentRuntimeResponse)
def get_execution_intent(
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
    publication_id: Annotated[
        str,
        Query(min_length=1, max_length=120),
    ],
    publication_version: Annotated[int, Query(ge=1)],
    execution_mode: ExecutionIntentMode,
    runtime: ExecutionIntentRuntime = Depends(get_execution_intent_runtime),
) -> ExecutionIntentRuntimeResponse:
    try:
        scope = ExecutionIntentScope(
            organization_id=organization_id,
            operational_unit_id=operational_unit_id,
            planning_date=planning_date,
            timezone=timezone,
            publication_id=publication_id,
            publication_version=publication_version,
            execution_mode=execution_mode,
        )
    except ValidationError as exc:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "INVALID_EXECUTION_INTENT_SCOPE",
                "message": "Scope Execution Intent non valido.",
            },
        ) from exc
    return ExecutionIntentRuntimeResponse.model_validate(
        runtime.current(scope).model_dump(mode="json")
    )
