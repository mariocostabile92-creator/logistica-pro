from datetime import date

from fastapi import APIRouter, HTTPException, Query, Request, status

from app.plugins.fleet.damage.application import service
from app.plugins.fleet.damage.interfaces.schemas import (
    DamageCreateRequest,
    DamageDriverSuggestionResponse,
    DamageNoteRequest,
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


@router.get("/damage-cases")
def damage_cases(
    status_value: str | None = Query(default=None, alias="status"),
    severity: str | None = None,
    vehicle_status: str | None = None,
    plate: str | None = None,
    driver: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    search: str | None = None,
):
    return guarded(service.list_cases, {
        "status": status_value, "severity": severity,
        "vehicle_operational_status": vehicle_status, "plate": plate,
        "driver": driver, "date_from": date_from, "date_to": date_to,
        "search": search,
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
