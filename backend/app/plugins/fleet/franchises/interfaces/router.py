from fastapi import APIRouter, HTTPException, Query, status

from app.plugins.fleet.franchises.application import service
from app.plugins.fleet.franchises.interfaces.schemas import (
    FranchiseCreateRequest,
    FranchiseUpdateRequest,
)

router = APIRouter(prefix="/api/fleet/franchises", tags=["fleet-franchises"])


def guarded(call, *args):
    try:
        return call(*args)
    except service.FranchiseError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


@router.get("")
def franchises(vehicle_id: int | None = Query(default=None, gt=0)):
    return guarded(service.list_cases, vehicle_id)


@router.get("/{case_id}")
def franchise(case_id: int):
    return guarded(service.get_case, case_id)


@router.post("", status_code=status.HTTP_201_CREATED)
def create_franchise(request: FranchiseCreateRequest):
    values = request.model_dump(mode="json")
    actor = str(values.pop("actor"))
    return guarded(service.ensure_for_damage, values, actor)


@router.patch("/{case_id}")
def update_franchise(case_id: int, request: FranchiseUpdateRequest):
    values = request.model_dump(exclude_unset=True, mode="json")
    actor = str(values.pop("actor", "fleet_manager"))
    return guarded(service.update_case, case_id, values, actor)
