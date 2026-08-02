from fastapi import APIRouter, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse

from app.auth import repository, service
from app.auth.permission_service import permissions_for
from app.auth.password_service import hash_password
from app.auth.schemas import BootstrapRequest, LoginRequest
from app.core.config import SETTINGS


router = APIRouter(prefix="/api/auth", tags=["authentication"])
COOKIE_NAME = "operations_session"


def _user_payload(user):
    return {
        "id": user.id,
        "email": user.email,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "role": user.role.value,
        "organization": {
            "id": user.organization_id,
            "name": user.organization_name,
        },
        "permissions": permissions_for(user.role),
    }


@router.get("/bootstrap/status")
def bootstrap_status():
    return {"required": repository.bootstrap_required()}


@router.post("/bootstrap", status_code=status.HTTP_201_CREATED)
def bootstrap(payload: BootstrapRequest, response: Response):
    if not repository.bootstrap_required():
        raise HTTPException(status_code=409, detail="Bootstrap gia completato.")
    try:
        user_id = repository.create_initial_setup(
            payload.organization.model_dump(), payload.administrator.model_dump(),
            hash_password(payload.administrator.password),
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except Exception as exc:
        if "unique" in str(exc).casefold():
            raise HTTPException(status_code=409, detail="Email gia utilizzata.") from exc
        raise
    row = repository.user_by_email(payload.administrator.email)
    user, token, expires_at = service.login(row["email"], payload.administrator.password, False)
    response.set_cookie(
        COOKIE_NAME, token, httponly=True, secure=SETTINGS.production,
        samesite="strict", path="/",
    )
    return {"user": _user_payload(user), "expires_at": expires_at.isoformat(), "id": user_id}


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
        response = JSONResponse(
            status_code=401,
            content={"detail": "Autenticazione richiesta."},
        )
        response.delete_cookie(COOKIE_NAME, path="/", samesite="strict")
        return response
    return {"user": _user_payload(user)}


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(request: Request, response: Response):
    session_id = getattr(request.state, "session_id", None)
    if session_id:
        repository.revoke_session(session_id)
    response.delete_cookie(COOKIE_NAME, path="/", samesite="strict")
