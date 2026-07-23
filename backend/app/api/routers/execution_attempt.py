from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import ValidationError

from app.api.dependencies.execution_attempt import (
    get_execution_attempt_runtime,
)
from app.domain.execution_attempt import ExecutionAttemptScope
from app.domain.execution_intent import ExecutionIntentId
from app.runtime.execution_attempt import ExecutionAttemptRuntime
from app.schemas.execution_attempt_schema import (
    ExecutionAttemptRuntimeResponse,
)


router = APIRouter(
    prefix="/api/runtime/execution-attempt",
    tags=["execution-attempt"],
)


@router.get("", response_model=ExecutionAttemptRuntimeResponse)
def get_execution_attempt(
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
    execution_intent_id: Annotated[
        str,
        Query(min_length=1, max_length=120),
    ],
    attempt_number: Annotated[int, Query(ge=1)],
    runtime: ExecutionAttemptRuntime = Depends(get_execution_attempt_runtime),
) -> ExecutionAttemptRuntimeResponse:
    try:
        scope = ExecutionAttemptScope(
            organization_id=organization_id,
            operational_unit_id=operational_unit_id,
            planning_date=planning_date,
            timezone=timezone,
            execution_intent_id=ExecutionIntentId(execution_intent_id),
            attempt_number=attempt_number,
        )
    except ValidationError as exc:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "INVALID_EXECUTION_ATTEMPT_SCOPE",
                "message": "Scope Execution Attempt non valido.",
            },
        ) from exc
    return ExecutionAttemptRuntimeResponse.model_validate(
        runtime.current(scope).model_dump(mode="json")
    )
