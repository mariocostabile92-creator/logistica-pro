from fastapi import APIRouter, HTTPException, Query, status

from app.plugins.fleet.insurance.application import service
from app.plugins.fleet.insurance.interfaces.schemas import (
    InsurancePolicyRequest,
    InsurancePolicyUpdateRequest,
)

router = APIRouter(prefix="/api/fleet/insurance-policies", tags=["fleet-insurance"])


def guarded(call, *args):
    try:
        return call(*args)
    except service.InsuranceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


@router.get("")
def policies(vehicle_id: int | None = Query(default=None, gt=0)):
    return guarded(service.list_policies, vehicle_id)


@router.get("/{policy_id}")
def policy(policy_id: int):
    return guarded(service.get_policy, policy_id)


@router.post("", status_code=status.HTTP_201_CREATED)
def create_policy(request: InsurancePolicyRequest):
    values = request.model_dump(mode="json")
    actor = str(values.pop("actor"))
    return guarded(service.create_policy, values, actor)


@router.patch("/{policy_id}")
def update_policy(policy_id: int, request: InsurancePolicyUpdateRequest):
    values = request.model_dump(exclude_unset=True, mode="json")
    actor = str(values.pop("actor", "fleet_manager"))
    return guarded(service.update_policy, policy_id, values, actor)
