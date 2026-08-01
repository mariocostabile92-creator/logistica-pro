import hmac

from fastapi import Request
from fastapi.responses import JSONResponse, RedirectResponse

from app.auth import repository
from app.auth.domain import AuthenticatedUser, Role
from app.auth.permission_service import has_permission
from app.auth.router import COOKIE_NAME
from app.core.config import SETTINGS


PUBLIC_EXACT = {
    "/api/health", "/api/auth/login", "/api/auth/session", "/api/auth/logout",
    "/api/auth/bootstrap/status", "/api/auth/bootstrap",
    "/app/login.html", "/app/bootstrap.html", "/app/journal", "/app/journal/",
}


def public_path(request: Request) -> bool:
    path = request.url.path
    if path in PUBLIC_EXACT or path.startswith("/app/assets/"):
        return True
    # The public Driver Journal uses the existing read-only asset catalogue to
    # offer plate selection. Mutating Fleet asset routes remain protected.
    if request.method in {"GET", "HEAD"} and path == "/api/plugins/fleet/v1/assets":
        return True
    if path.startswith("/app/journal/"):
        return True
    if path.startswith("/api/plugins/fleet/v1/journal/"):
        return not path.startswith("/api/plugins/fleet/v1/journal/vehicles/")
    return False


async def enforce_authentication(request: Request, call_next):
    path = request.url.path
    auth_optional = path in {"/api/auth/session", "/api/auth/logout"}
    if path == "/app/login.html" and repository.bootstrap_required():
        return RedirectResponse("/app/bootstrap.html", status_code=303)
    if path == "/app/bootstrap.html" and not repository.bootstrap_required():
        return RedirectResponse("/app/login.html", status_code=303)
    if public_path(request) and not auth_optional:
        return await call_next(request)
    # The legacy suite installs a random, process-local harness token. A normal
    # application process never has this state and therefore has no test bypass.
    harness_token = getattr(request.app.state, "test_auth_harness_token", None)
    supplied_token = request.headers.get("X-Test-Auth-Harness", "")
    if (
        SETTINGS.environment == "test"
        and harness_token
        and supplied_token
        and hmac.compare_digest(supplied_token, harness_token)
        and request.headers.get("X-Auth-Enforce") != "1"
    ):
        request.state.user = AuthenticatedUser(
            id="test-harness-administrator", email="harness@example.test",
            role=Role.ADMINISTRATOR, organization_id="test-organization",
            organization_name="Test Organization",
        )
        request.state.organization_id = "test-organization"
        return await call_next(request)
    resolved = None
    token = request.cookies.get(COOKIE_NAME)
    if token:
        resolved = repository.user_by_session(token)
    if resolved:
        user, session_id = resolved
        request.state.user = user
        request.state.session_id = session_id
        request.state.organization_id = user.organization_id
    if auth_optional:
        return await call_next(request)
    if not resolved:
        if path.startswith("/api/"):
            return JSONResponse(status_code=401, content={"detail": "Autenticazione richiesta."})
        if path in {"/", "/app", "/app/"}:
            target = "/app/bootstrap.html" if repository.bootstrap_required() else "/app/login.html"
            return RedirectResponse(target, status_code=303)
        return await call_next(request)
    user, session_id = resolved
    required = "admin:read" if request.method in {"GET", "HEAD", "OPTIONS"} else "admin:write"
    if path.startswith("/api/") and not has_permission(user.role, required):
        return JSONResponse(status_code=403, content={"detail": "Permesso insufficiente."})
    response = await call_next(request)
    if path.startswith("/api/") and request.method not in {"GET", "HEAD", "OPTIONS"}:
        repository.record_audit(user, request.method, path, response.status_code)
    return response
