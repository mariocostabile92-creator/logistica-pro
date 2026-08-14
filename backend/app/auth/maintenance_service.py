import hashlib
import hmac
import secrets
import uuid
from datetime import UTC, datetime, timedelta

from app.auth import maintenance_repository as repository
from app.auth.maintenance_domain import (
    MaintenancePrincipal,
    MaintenanceScope,
    MaintenanceTokenCreated,
    MaintenanceTokenStatus,
)
from app.core.config import SETTINGS


DEFAULT_TTL_MINUTES = 15
MAX_TTL_MINUTES = 30
TOKEN_PREFIX = "omt_v1_"
_PROCESS_FALLBACK_KEY = secrets.token_bytes(32)


class MaintenanceTokenError(RuntimeError):
    pass


class MaintenanceTokenInvalidError(MaintenanceTokenError):
    pass


class MaintenanceTokenNotFoundError(MaintenanceTokenError):
    pass


def _now() -> datetime:
    return datetime.now(UTC)


def _hash_key() -> bytes:
    return (
        SETTINGS.secret_key.encode("utf-8")
        if SETTINGS.secret_key
        else _PROCESS_FALLBACK_KEY
    )


def token_hash(raw_token: str) -> str:
    return hmac.new(
        _hash_key(), raw_token.encode("utf-8"), hashlib.sha256
    ).hexdigest()


def create_token(
    *,
    organization_id: str,
    created_by: str,
    scope: MaintenanceScope,
    ttl_minutes: int = DEFAULT_TTL_MINUTES,
) -> MaintenanceTokenCreated:
    if ttl_minutes < 1 or ttl_minutes > MAX_TTL_MINUTES:
        raise MaintenanceTokenError("La durata deve essere compresa tra 1 e 30 minuti.")
    created = _now()
    expires = created + timedelta(minutes=ttl_minutes)
    raw_token = TOKEN_PREFIX + secrets.token_urlsafe(48)
    token_id = str(uuid.uuid4())
    try:
        repository.create(
            token_id=token_id,
            organization_id=organization_id,
            token_hash=token_hash(raw_token),
            scope=scope.value,
            created_by=created_by,
            created_at=created.isoformat(),
            expires_at=expires.isoformat(),
        )
    except repository.MaintenanceTokenLimitError as exc:
        raise MaintenanceTokenError(str(exc)) from exc
    return MaintenanceTokenCreated(
        id=token_id,
        token=raw_token,
        scope=scope,
        expires_at=expires.isoformat(),
    )


def authenticate(raw_token: str, required_scope: MaintenanceScope) -> MaintenancePrincipal:
    if not raw_token or not raw_token.startswith(TOKEN_PREFIX):
        raise MaintenanceTokenInvalidError("Credenziali di manutenzione non valide.")
    row = repository.find_by_hash(token_hash(raw_token))
    if not row:
        raise MaintenanceTokenInvalidError("Credenziali di manutenzione non valide.")
    now = _now()
    expires_at = datetime.fromisoformat(row["expires_at"])
    if (
        row["status"] != MaintenanceTokenStatus.ACTIVE.value
        or row["revoked_at"] is not None
        or expires_at <= now
    ):
        if row["status"] == MaintenanceTokenStatus.ACTIVE.value and expires_at <= now:
            repository.expire(row["id"], row["organization_id"], now.isoformat())
        raise MaintenanceTokenInvalidError("Credenziali di manutenzione non valide.")
    if not hmac.compare_digest(row["scope"], required_scope.value):
        raise MaintenanceTokenInvalidError("Credenziali di manutenzione non valide.")
    return MaintenancePrincipal(
        token_id=row["id"],
        organization_id=row["organization_id"],
        scope=MaintenanceScope(row["scope"]),
        created_by=row["created_by"],
    )


def raw_bearer(authorization: str | None) -> str:
    if not authorization:
        raise MaintenanceTokenInvalidError("Credenziali di manutenzione non valide.")
    scheme, separator, value = authorization.partition(" ")
    if not separator or scheme.casefold() != "bearer" or not value.strip():
        raise MaintenanceTokenInvalidError("Credenziali di manutenzione non valide.")
    return value.strip()


def record_usage(
    principal: MaintenancePrincipal,
    *,
    method: str,
    path: str,
    status_code: int,
) -> None:
    repository.record_usage(
        token_id=principal.token_id,
        organization_id=principal.organization_id,
        created_by=principal.created_by,
        scope=principal.scope.value,
        endpoint=f"{method} {path}",
        status_code=status_code,
        used_at=_now().isoformat(),
    )


def revoke_token(*, token_id: str, organization_id: str, revoked_by: str) -> None:
    if not repository.revoke(
        token_id=token_id,
        organization_id=organization_id,
        revoked_by=revoked_by,
        revoked_at=_now().isoformat(),
    ):
        raise MaintenanceTokenNotFoundError("Token di manutenzione non trovato.")

