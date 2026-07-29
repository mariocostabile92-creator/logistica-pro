from fastapi import APIRouter, HTTPException, Query, status

from app.plugins.fleet.damage.application import service
from app.plugins.fleet.damage.interfaces.schemas import (
    DamageCreateRequest,
    DamageNoteRequest,
    DamageStatusRequest,
    DamageUpdateRequest,
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


@router.get("/damage-cases/{case_id}")
def damage_case(case_id: int):
    return guarded(service.get_case, case_id)


@router.post("/damage-cases", status_code=status.HTTP_201_CREATED)
def create_damage_case(request: DamageCreateRequest):
    values = request.model_dump(mode="json")
    actor = str(values.pop("actor"))
    return guarded(service.create_case, values, actor)


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
