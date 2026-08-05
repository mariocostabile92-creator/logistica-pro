from contextvars import ContextVar, Token
import os


_organization_id: ContextVar[str | None] = ContextVar(
    "operations_organization_id",
    default=None,
)


def bind_organization(organization_id: str) -> Token[str | None]:
    if not organization_id:
        raise ValueError("organization_id is required for authenticated data access.")
    return _organization_id.set(organization_id)


def reset_organization(token: Token[str | None]) -> None:
    _organization_id.reset(token)


def current_organization_id(default: str = "default") -> str:
    organization_id = _organization_id.get()
    if organization_id:
        return organization_id
    if os.getenv("APP_ENV", "").strip().casefold() == "test":
        return "test-organization"
    return default
