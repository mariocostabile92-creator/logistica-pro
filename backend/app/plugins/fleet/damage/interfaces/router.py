from datetime import date
import json

from fastapi import APIRouter, HTTPException, Query, Request, status

from app.auth import repository as auth_repository
from app.auth.permission_service import has_permission
from app.plugins.fleet.damage.application import service
from app.plugins.fleet.damage.application import (
    damage_counter_service,
    damage_policy_service,
)
from app.plugins.fleet.damage.domain.damage_policy import DamagePolicy
from app.plugins.fleet.damage.interfaces.schemas import (
    DamageCreateRequest,
    DamageDriverPolicyStateResponse,
    DamageDriverSuggestionResponse,
    DamageNoteRequest,
    DamagePolicyResponse,
    DamagePolicyUpdateRequest,
    DamageStatusRequest,
    DamageUpdateRequest,
    ManualOperationalStatusRequest,
)

router = APIRouter(prefix="/api/fleet", tags=["fleet-damage"])


def guarded(call, *args):
    try:
        return call(*args)
    except service.DamageError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


def _policy_payload(policy: DamagePolicy) -> dict:
    return policy.model_dump(
        mode="json",
        include={"enabled", "free_events_count", "counting_period", "updated_at"},
    )


def _require_policy_write(request: Request):
    user = request.state.user
    if not has_permission(user.role, "admin:write"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Permesso di configurazione richiesto.",
        )
    return user


@router.get("/damage-cases")
def damage_cases(
    status_value: str | None = Query(default=None, alias="status"),
    severity: str | None = None,
    vehicle_status: str | None = None,
    plate: str | None = None,
    driver: str | None = None,
    workforce_member_id: int | None = Query(default=None, gt=0),
    driver_unassigned: bool = False,
    date_from: str | None = None,
    date_to: str | None = None,
    search: str | None = None,
):
    return guarded(service.list_cases, {
        "status": status_value, "severity": severity,
        "vehicle_operational_status": vehicle_status, "plate": plate,
        "driver": driver, "date_from": date_from, "date_to": date_to,
        "search": search, "workforce_member_id": workforce_member_id,
        "driver_unassigned": driver_unassigned,
    })


@router.get(
    "/damage-cases/driver-suggestion",
    response_model=DamageDriverSuggestionResponse,
)
def damage_driver_suggestion(
    request: Request,
    vehicle_id: int = Query(gt=0),
    operational_date: date = Query(),
):
    return guarded(
        service.suggest_driver,
        vehicle_id,
        operational_date.isoformat(),
        str(request.state.user.organization_id),
    )


@router.get(
    "/damage-cases/policy",
    response_model=DamagePolicyResponse,
)
def get_damage_policy(request: Request):
    policy = damage_policy_service.current_policy(
        str(request.state.user.organization_id)
    )
    return _policy_payload(policy)


@router.put(
    "/damage-cases/policy",
    response_model=DamagePolicyResponse,
)
def update_damage_policy(payload: DamagePolicyUpdateRequest, request: Request):
    actor = _require_policy_write(request)
    organization_id = str(actor.organization_id)
    previous = damage_policy_service.current_policy(organization_id)
    saved = damage_policy_service.save_policy(DamagePolicy(
        organization_id=organization_id,
        **payload.model_dump(),
    ))
    auth_repository.record_audit(
        actor,
        "damage_policy_changed",
        json.dumps(
            {"old": _policy_payload(previous), "new": _policy_payload(saved)},
            ensure_ascii=False,
            sort_keys=True,
        ),
        status.HTTP_200_OK,
    )
    return _policy_payload(saved)


@router.get(
    "/damage-cases/drivers/{workforce_member_id}/policy-state",
    response_model=DamageDriverPolicyStateResponse,
)
def damage_driver_policy_state(
    workforce_member_id: int,
    request: Request,
    reference_date: date | None = None,
):
    try:
        state = damage_counter_service.driver_policy_state(
            str(request.state.user.organization_id),
            workforce_member_id,
            reference_date,
        )
    except damage_counter_service.DamagePolicyDriverNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return state.model_dump(mode="json", exclude={"workforce_member_id"})


@router.get("/damage-cases/{case_id}")
def damage_case(case_id: int):
    return guarded(service.get_case, case_id)


@router.post("/damage-cases", status_code=status.HTTP_201_CREATED)
def create_damage_case(payload: DamageCreateRequest, request: Request):
    values = payload.model_dump(mode="json")
    actor = str(values.pop("actor"))
    return guarded(
        service.create_case,
        values,
        actor,
        str(request.state.user.id),
    )


@router.patch("/damage-cases/{case_id}")
def update_damage_case(case_id: int, request: DamageUpdateRequest):
    values = request.model_dump(exclude_unset=True, mode="json")
    actor = str(values.pop("actor", "fleet_manager"))
    return guarded(service.update_case, case_id, values, actor)


@router.post("/damage-cases/{case_id}/status")
def update_damage_status(case_id: int, request: DamageStatusRequest):
    return guarded(
        service.change_status, case_id, request.status, request.note,
        request.actor, request.restoration_status,
    )


@router.post("/damage-cases/{case_id}/notes")
def add_damage_note(case_id: int, request: DamageNoteRequest):
    return guarded(service.add_note, case_id, request.note, request.actor)


@router.get("/damage-cases/{case_id}/events")
def damage_events(case_id: int):
    return guarded(service.events, case_id)


@router.get("/damage-candidates")
def damage_candidates():
    return guarded(service.list_candidates)


@router.patch("/vehicles/{vehicle_id}/operational-status")
def manual_operational_status(
    vehicle_id: int,
    request: ManualOperationalStatusRequest,
):
    try:
        return service.operational_status_service.manual_change(
            vehicle_id=vehicle_id,
            **request.model_dump(),
        )
    except service.operational_status_service.ManualStatusConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except (ValueError, service.AssetNotFoundError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
