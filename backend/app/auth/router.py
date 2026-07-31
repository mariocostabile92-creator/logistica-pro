from fastapi import APIRouter, HTTPException, Request, Response, status

from app.auth import repository, service
from app.auth.permission_service import permissions_for
from app.auth.schemas import LoginRequest
from app.core.config import SETTINGS


router = APIRouter(prefix="/api/auth", tags=["authentication"])
COOKIE_NAME = "operations_session"


def _user_payload(user):
    return {
        "id": user.id,
        "email": user.email,
        "role": user.role.value,
        "organization": {
            "id": user.organization_id,
            "name": user.organization_name,
        },
        "permissions": permissions_for(user.role),
    }


@router.post("/login")
def login(payload: LoginRequest, response: Response):
    try:
        user, token, expires_at = service.login(
            payload.email, payload.password, payload.remember_me
        )
    except service.InvalidCredentialsError as exc:
        raise HTTPException(status_code=401, detail="Credenziali non valide.") from exc
    response.set_cookie(
        COOKIE_NAME, token, httponly=True, secure=SETTINGS.production,
        samesite="strict", expires=expires_at if payload.remember_me else None,
        path="/",
    )
    return {"user": _user_payload(user), "expires_at": expires_at.isoformat()}


@router.get("/session")
def session(request: Request):
    user = getattr(request.state, "user", None)
    if not user:
        raise HTTPException(status_code=401, detail="Autenticazione richiesta.")
    return {"user": _user_payload(user)}


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(request: Request, response: Response):
    session_id = getattr(request.state, "session_id", None)
    if session_id:
        repository.revoke_session(session_id)
    response.delete_cookie(COOKIE_NAME, path="/", samesite="strict")

