from fastapi import APIRouter, HTTPException, Request

from app.auth.domain import Role
from app.schemas.planning_operations_schema import (
    ConvocationRequest,
    ForecastRequest,
    OperationalLifecycleRequest,
    PlanningOperationResponse,
)
from app.services.planning_operations_service import (
    PlanningOperationError,
    operational_snapshot,
    save_forecast,
    transition,
    update_convocation,
)
from app.plugins.workforce.application.foundation_service import foundation_snapshot
from app.plugins.workforce.application.planning_adapter import (
    planning_conflicts,
    planning_contract,
)


router = APIRouter(prefix="/api/planning/operations", tags=["planning-operations"])
WRITE_ROLES = {Role.ADMINISTRATOR, Role.OPERATIONS_MANAGER, Role.DISPATCHER}


def _user(request: Request):
    return request.state.user


def _require_write(request: Request):
    user = _user(request)
    if user.role not in WRITE_ROLES:
        raise HTTPException(status_code=403, detail="Planning disponibile in sola lettura.")
    return user


@router.get("", response_model=PlanningOperationResponse)
def snapshot(request: Request) -> PlanningOperationResponse:
    user = _user(request)
    payload = operational_snapshot(
        can_write=user.role in WRITE_ROLES,
        is_admin=user.role is Role.ADMINISTRATOR,
    )
    operation_date = (
        payload["planning"].get("operation_date") if payload["planning"]
        else (payload.get("forecast") or {}).get("period_start")
    )
    workforce = foundation_snapshot(operation_date, user.organization_id)
    payload["workforce"] = workforce.model_dump(mode="json")
    payload["workforce"]["planning"] = planning_contract(workforce)
    consecutivity_conflicts = planning_conflicts(workforce, payload["routes"])
    payload["conflicts"] = [*payload["conflicts"], *consecutivity_conflicts]
    payload["summary"]["conflicts"] = len(payload["conflicts"])
    payload["summary"]["blocking_conflicts"] = sum(
        bool(item.get("blocking")) for item in payload["conflicts"]
    )
    if consecutivity_conflicts:
        payload["lifecycle"]["can_confirm"] = (
            payload["lifecycle"]["can_confirm"]
            and not any(item["blocking"] for item in consecutivity_conflicts)
        )
    return PlanningOperationResponse.model_validate(payload)


@router.get("/summary")
def summary(request: Request):
    user = _user(request)
    payload = operational_snapshot(
        can_write=user.role in WRITE_ROLES,
        is_admin=user.role is Role.ADMINISTRATOR,
    )
    return {
        "planning": payload["planning"],
        "summary": payload["summary"],
        "lifecycle": payload["lifecycle"],
    }


@router.post("/forecast")
def create_forecast(payload: ForecastRequest, request: Request):
    _require_write(request)
    return save_forecast(payload)


@router.patch("/{planning_id}/convocations/{assignment_id}")
def patch_convocation(
    planning_id: int,
    assignment_id: int,
    payload: ConvocationRequest,
    request: Request,
):
    user = _require_write(request)
    try:
        return update_convocation(
            planning_id,
            assignment_id,
            status=payload.status,
            scheduled_time=payload.scheduled_time,
            actor=user.email,
        )
    except PlanningOperationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/{planning_id}/confirm")
def confirm(
    planning_id: int,
    payload: OperationalLifecycleRequest,
    request: Request,
):
    user = _require_write(request)
    try:
        return transition(planning_id, "confirmed", payload.actor or user.email)
    except PlanningOperationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/{planning_id}/publish")
def publish(
    planning_id: int,
    payload: OperationalLifecycleRequest,
    request: Request,
):
    user = _require_write(request)
    try:
        return transition(planning_id, "published", payload.actor or user.email)
    except PlanningOperationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
