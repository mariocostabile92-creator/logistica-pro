import hmac
import re

from fastapi import Request
from fastapi.responses import JSONResponse, RedirectResponse

from app.auth import repository
from app.auth.domain import AuthenticatedUser, Role
from app.auth.maintenance_domain import MaintenanceScope
from app.auth import maintenance_service
from app.auth.permission_service import has_permission
from app.auth.router import COOKIE_NAME
from app.auth.tenant_context import bind_organization, reset_organization
from app.core.config import SETTINGS


PUBLIC_EXACT = {
    "/api/health", "/api/auth/login", "/api/auth/session", "/api/auth/logout",
    "/api/auth/bootstrap/status", "/api/auth/bootstrap", "/api/auth/register",
    "/app/login.html", "/app/bootstrap.html", "/app/journal", "/app/journal/",
}


PUBLIC_JOURNAL_ROUTES = (
    ({"GET", "HEAD"}, re.compile(r"^/api/plugins/fleet/v1/journal/(configuration|assets)$")),
    ({"POST"}, re.compile(r"^/api/plugins/fleet/v1/journal/sessions/shared$")),
    ({"GET", "HEAD"}, re.compile(r"^/api/plugins/fleet/v1/journal/sessions/[^/]+$")),
    ({"POST"}, re.compile(r"^/api/plugins/fleet/v1/journal/sessions/[^/]+/(progress|warnings|media|complete)$")),
    ({"DELETE"}, re.compile(r"^/api/plugins/fleet/v1/journal/sessions/[^/]+/media/[^/]+$")),
    ({"GET", "HEAD"}, re.compile(r"^/api/plugins/fleet/v1/journal/(movements/[^/]+/receipt|media/[^/]+|shared-access/[^/]+)$")),
)


MAINTENANCE_ROUTES = {
    ("GET", "/api/plugins/workforce/v1/planning/coverage"):
        MaintenanceScope.PLANNING_COVERAGE_BACKFILL,
    ("POST", "/api/plugins/workforce/v1/planning/coverage/backfill/preview"):
        MaintenanceScope.PLANNING_COVERAGE_BACKFILL,
    ("POST", "/api/plugins/workforce/v1/planning/coverage/backfill"):
        MaintenanceScope.PLANNING_COVERAGE_BACKFILL,
}


def _public_journal_path(request: Request) -> bool:
    return any(
        request.method in methods and pattern.fullmatch(request.url.path)
        for methods, pattern in PUBLIC_JOURNAL_ROUTES
    )


def _required_permission(path: str, method: str) -> str:
    reading = method in {"GET", "HEAD", "OPTIONS"}
    if path.startswith("/api/attachments"):
        return "attachments:read" if reading else "attachments:write"
    if path.startswith("/api/fleet/journal") or path.startswith("/api/plugins/fleet/v1/journal"):
        return "journal:read" if reading else "journal:write"
    if path.startswith("/api/fleet") or path.startswith("/api/plugins/fleet/v1"):
        return "fleet:read" if reading else "fleet:write"
    if path.startswith("/api/plugins/workforce"):
        return "workforce:read" if reading else "workforce:write"
    if path.startswith(("/api/planning", "/api/operations", "/api/imports")):
        return "planning:read" if reading else "planning:write"
    return "admin:read" if reading else "admin:write"


def public_path(request: Request) -> bool:
    path = request.url.path
    if path in PUBLIC_EXACT or path.startswith("/app/assets/"):
        return True
    if path.startswith("/app/driver-shifts") or path.startswith("/api/public/driver-shifts/"):
        return True
    if path.startswith("/app/journal/"):
        return True
    if path.startswith("/api/plugins/fleet/v1/journal/"):
        return _public_journal_path(request)
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
        tenant_token = bind_organization(request.state.organization_id)
        try:
            return await call_next(request)
        finally:
            reset_organization(tenant_token)
    resolved = None
    token = request.cookies.get(COOKIE_NAME)
    if token:
        resolved = repository.user_by_session(token)
    maintenance_scope = MAINTENANCE_ROUTES.get((request.method, path))
    maintenance_principal = None
    session_is_administrator = bool(
        resolved and resolved[0].role == Role.ADMINISTRATOR
    )
    if maintenance_scope and not session_is_administrator:
        authorization = request.headers.get("authorization")
        if authorization:
            try:
                maintenance_principal = maintenance_service.authenticate(
                    maintenance_service.raw_bearer(authorization),
                    maintenance_scope,
                )
            except maintenance_service.MaintenanceTokenInvalidError:
                return JSONResponse(
                    status_code=401,
                    content={"detail": "Credenziali di manutenzione non valide."},
                )
    if maintenance_principal is not None:
        request.state.maintenance_principal = maintenance_principal
        request.state.organization_id = maintenance_principal.organization_id
        tenant_token = bind_organization(maintenance_principal.organization_id)
        try:
            response = await call_next(request)
            maintenance_service.record_usage(
                maintenance_principal,
                method=request.method,
                path=path,
                status_code=response.status_code,
            )
            return response
        finally:
            reset_organization(tenant_token)
    if resolved:
        user, session_id = resolved
        request.state.user = user
        request.state.session_id = session_id
        request.state.organization_id = user.organization_id
    if auth_optional:
        if not resolved:
            return await call_next(request)
        tenant_token = bind_organization(request.state.organization_id)
        try:
            return await call_next(request)
        finally:
            reset_organization(tenant_token)
    if not resolved:
        if path.startswith("/api/"):
            return JSONResponse(status_code=401, content={"detail": "Autenticazione richiesta."})
        if path in {"/", "/app", "/app/"}:
            target = "/app/bootstrap.html" if repository.bootstrap_required() else "/app/login.html"
            return RedirectResponse(target, status_code=303)
        return await call_next(request)
    user, session_id = resolved
    required = _required_permission(path, request.method)
    if path.startswith("/api/") and not has_permission(user.role, required):
        return JSONResponse(status_code=403, content={"detail": "Permesso insufficiente."})
    tenant_token = bind_organization(user.organization_id)
    try:
        response = await call_next(request)
        if path.startswith("/api/") and request.method not in {"GET", "HEAD", "OPTIONS"}:
            repository.record_audit(user, request.method, path, response.status_code)
        return response
    finally:
        reset_organization(tenant_token)
