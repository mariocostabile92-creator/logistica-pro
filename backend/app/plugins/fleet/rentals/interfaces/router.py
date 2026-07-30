from fastapi import APIRouter, HTTPException, Query, status

from app.plugins.fleet.rentals.application import service
from app.plugins.fleet.rentals.interfaces.schemas import (
    RentalCreateRequest,
    RentalUpdateRequest,
)

router = APIRouter(prefix="/api/fleet/rentals", tags=["fleet-rentals"])


def guarded(call, *args):
    try:
        return call(*args)
    except service.RentalError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


@router.get("")
def rentals(vehicle_id: int | None = Query(default=None, gt=0)):
    return guarded(service.list_rentals, vehicle_id)


@router.get("/{rental_id}")
def rental(rental_id: int):
    return guarded(service.get_rental, rental_id)


@router.post("", status_code=status.HTTP_201_CREATED)
def create_rental(request: RentalCreateRequest):
    values = request.model_dump(mode="json")
    actor = str(values.pop("actor"))
    return guarded(service.create_rental, values, actor)


@router.patch("/{rental_id}")
def update_rental(rental_id: int, request: RentalUpdateRequest):
    values = request.model_dump(exclude_unset=True, mode="json")
    actor = str(values.pop("actor", "fleet_manager"))
    return guarded(service.update_rental, rental_id, values, actor)
