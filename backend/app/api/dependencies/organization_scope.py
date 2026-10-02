from fastapi import HTTPException, Request

from app.auth.domain import AuthenticatedUser


def authenticated_organization_id(request: Request) -> str:
    """Use the authenticated principal, never a client scope or tenant fallback."""
    user = getattr(request.state, "user", None)
    if not isinstance(user, AuthenticatedUser) or not user.organization_id:
        raise HTTPException(status_code=401, detail="Autenticazione richiesta.")
    return user.organization_id


def authorize_organization_scope(
    requested_organization_id: str,
    authenticated_organization_id: str,
) -> str:
    # Existing clients send "default" for their workspace. It is an alias for
    # the session tenant, NOT permission to read/write the stored default tenant.
    if requested_organization_id not in {"default", authenticated_organization_id}:
        raise HTTPException(status_code=403, detail="Permesso insufficiente.")
    return authenticated_organization_id
