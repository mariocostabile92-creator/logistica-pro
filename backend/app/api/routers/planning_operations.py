from datetime import date

from fastapi import APIRouter, HTTPException, Query, Request

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
from app.api.planning_workforce_bridge import planning_workforce_input
from app.plugins.workforce.application.foundation_service import foundation_snapshot
from app.plugins.workforce.application.planning_adapter import (
    planning_conflicts,
    planning_contract,
)
from app.plugins.fleet.application.daily_capacity_service import (
    daily_fleet_capacity,
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
def snapshot(
    request: Request,
    operation_date: date = Query(default_factory=date.today),
) -> PlanningOperationResponse:
    user = _user(request)
    day = operation_date.isoformat()
    payload = operational_snapshot(
        operation_date=day,
        can_write=user.role in WRITE_ROLES,
        is_admin=user.role is Role.ADMINISTRATOR,
    )
    workforce_input = planning_workforce_input(
        operation_date=day,
        organization_id=user.organization_id,
    )
    payload["workforce"] = workforce_input
    payload["coverage"] = workforce_input["coverage"]
    planning_station = (
        str(payload["planning"].get("station") or "").strip() or None
        if payload.get("planning")
        else None
    )
    payload["fleet_capacity"] = daily_fleet_capacity(
        organization_id=str(user.organization_id),
        operational_date=day,
        requested_station=planning_station,
        coverage_items=workforce_input["coverage"]["items"],
        route_assignments_available=bool(payload["route_data_available"]),
        assigned_vehicles=(
            int(payload["summary"].get("vehicles_assigned") or 0)
            if payload["route_data_available"]
            else None
        ),
        routes_without_vehicle=(
            sum(not bool(route.get("plate")) for route in payload["routes"])
            if payload["route_data_available"]
            else None
        ),
    ).model_dump(mode="json")
    coverage_summary = workforce_input["coverage"]["summary"]
    payload["summary"]["routes_forecast"] = (
        coverage_summary["forecast_total"]
        if workforce_input["coverage"]["available"]
        else None
    )
    payload["summary"]["requirement"] = (
        coverage_summary["requirement_total"]
        if workforce_input["coverage"]["available"]
        else None
    )
    payload["summary"]["drivers_planned"] = workforce_input["summary"]["planned"]
    payload["summary"]["requirement_gap"] = (
        coverage_summary["requirement_gap_total"]
        if workforce_input["coverage"]["available"]
        else None
    )
    if payload["planning"] and payload["lifecycle"]["state"] in {"confirmed", "published"}:
        readiness_state = payload["lifecycle"]["state"].upper()
    elif not workforce_input["summary"]["planned"]:
        readiness_state = "WORKFORCE_MISSING"
    elif not workforce_input["coverage"]["available"]:
        readiness_state = "FORECAST_MISSING"
    elif not payload["route_data_available"]:
        readiness_state = "ROUTES_MISSING"
    elif not payload["vehicle_assignments_available"]:
        readiness_state = "VEHICLES_MISSING"
    else:
        readiness_state = "READY_FOR_CONFIRMATION"
    payload["readiness"] = {
        "state": readiness_state,
        "workforce_planning_available": bool(workforce_input["summary"]["planned"]),
        "forecast_available": workforce_input["coverage"]["available"],
        "requirement_covered": workforce_input["coverage"]["requirement_covered"],
        "route_data_available": payload["route_data_available"],
        "vehicle_assignments_available": payload["vehicle_assignments_available"],
    }

    consecutivity_conflicts = []
    if payload["planning"]:
        workforce = foundation_snapshot(day, user.organization_id)
        payload["workforce"]["planning"] = planning_contract(workforce)
        consecutivity_conflicts = planning_conflicts(workforce, payload["routes"])
    payload["conflicts"] = [*payload["conflicts"], *consecutivity_conflicts]
    if payload["route_data_available"]:
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
        operation_date=date.today().isoformat(),
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
