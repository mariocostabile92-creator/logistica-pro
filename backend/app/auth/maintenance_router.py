from fastapi import APIRouter, HTTPException, Request, Response, status

from app.auth.domain import Role
from app.auth.maintenance_domain import (
    MaintenanceTokenCreateRequest,
    MaintenanceTokenCreated,
)
from app.auth import maintenance_service


router = APIRouter(prefix="/api/admin/maintenance-tokens", tags=["maintenance-tokens"])
NO_STORE_HEADERS = {
    "Cache-Control": "no-store, private, max-age=0",
    "Pragma": "no-cache",
}


def _administrator(request: Request):
    user = request.state.user
    if user.role != Role.ADMINISTRATOR:
        raise HTTPException(status_code=403, detail="Permesso Administrator richiesto.")
    return user


@router.post("", response_model=MaintenanceTokenCreated, status_code=status.HTTP_201_CREATED)
def create_maintenance_token(
    payload: MaintenanceTokenCreateRequest,
    request: Request,
    response: Response,
) -> MaintenanceTokenCreated:
    user = _administrator(request)
    try:
        created = maintenance_service.create_token(
            organization_id=user.organization_id,
            created_by=user.id,
            scope=payload.scope,
            ttl_minutes=payload.ttl_minutes,
        )
    except maintenance_service.MaintenanceTokenError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    response.headers.update(NO_STORE_HEADERS)
    return created


@router.post("/{token_id}/revoke", status_code=status.HTTP_204_NO_CONTENT)
def revoke_maintenance_token(
    token_id: str, request: Request
) -> Response:
    user = _administrator(request)
    try:
        maintenance_service.revoke_token(
            token_id=token_id,
            organization_id=user.organization_id,
            revoked_by=user.id,
        )
    except maintenance_service.MaintenanceTokenNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT, headers=NO_STORE_HEADERS)
