from fastapi import APIRouter, HTTPException, Request, Response, status

from app.auth import organization_service
from app.auth.permission_service import has_permission
from app.auth.schemas import PasswordChangeRequest, UserCreateRequest, UserUpdateRequest


router = APIRouter(prefix="/api/organization", tags=["organization-settings"])


def administrator(request: Request):
    user = request.state.user
    if not has_permission(user.role, "users:manage"):
        raise HTTPException(status_code=403, detail="Permesso Administrator richiesto.")
    return user


def guarded(call, *args):
    try:
        return call(*args)
    except organization_service.OrganizationError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


@router.get("")
def get_organization(request: Request):
    return guarded(organization_service.organization, administrator(request))


@router.get("/users")
def list_users(request: Request):
    return {"items": guarded(organization_service.users, administrator(request))}


@router.post("/users", status_code=status.HTTP_201_CREATED)
def create_user(payload: UserCreateRequest, request: Request):
    return guarded(organization_service.create_user, administrator(request), payload.model_dump())


@router.patch("/users/{user_id}")
def update_user(user_id: str, payload: UserUpdateRequest, request: Request):
    return guarded(
        organization_service.update_user, administrator(request), user_id, payload.model_dump()
    )


@router.post("/users/{user_id}/password", status_code=status.HTTP_204_NO_CONTENT)
def change_password(user_id: str, payload: PasswordChangeRequest, request: Request):
    guarded(organization_service.change_password, administrator(request), user_id, payload.password)
    return Response(status_code=204)
