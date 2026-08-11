import hashlib
import hmac
import secrets

from app.core.config import SETTINGS
from app.plugins.workforce.application.driver_shift_distribution_service import _expires_at
from app.plugins.workforce.domain.driver_shift_portal import (
    DriverShiftPortalAccess,
    DriverShiftPortalAvailability,
    DriverShiftPortalInvalidError,
)
from app.plugins.workforce.infrastructure import driver_shift_portal_repository as repository


def _key() -> bytes:
    return (SETTINGS.secret_key or "operations-engine-development-driver-shifts").encode("utf-8")


def _token(public_id: str, generation: int) -> str:
    payload = f"portal.{public_id}.{generation}"
    signature = hmac.new(_key(), payload.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"{public_id}.{generation}.{signature}"


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _new_identity(generation: int = 1) -> tuple[str, str, str]:
    public_id = secrets.token_urlsafe(24)
    token = _token(public_id, generation)
    return public_id, token, _token_hash(token)


def _access(row: dict) -> DriverShiftPortalAccess:
    token = _token(str(row["public_id"]), int(row["token_generation"]))
    if not hmac.compare_digest(_token_hash(token), str(row["token_hash"])):
        raise DriverShiftPortalInvalidError("Portale condiviso non coerente: rigeneralo.")
    access_url = None
    if row["status"] == "ACTIVE":
        access_url = f"{SETTINGS.base_url}/app/driver-shifts/access/#token={token}"
    return DriverShiftPortalAccess(
        id=int(row["id"]),
        distribution_id=int(row["distribution_id"]),
        status=str(row["status"]),
        access_url=access_url,
        expires_at=str(row["expires_at"]),
        created_at=str(row["created_at"]),
        created_by=str(row["created_by"]),
        revoked_at=row.get("revoked_at"),
    )


def get_portal(organization_id: str, distribution_id: int) -> DriverShiftPortalAccess:
    return _access(repository.portal_for_distribution(organization_id, distribution_id))


def prepare_portal(organization_id: str, distribution_id: int,
                   actor: str) -> DriverShiftPortalAccess:
    period_end = repository.distribution_period_end(organization_id, distribution_id)
    public_id, _, token_hash = _new_identity()
    row = repository.prepare_portal(
        organization_id, distribution_id, public_id, token_hash,
        _expires_at(period_end), actor,
    )
    return _access(row)


def revoke_portal(organization_id: str, distribution_id: int,
                  actor: str) -> DriverShiftPortalAccess:
    return _access(repository.revoke_portal(organization_id, distribution_id, actor))


def regenerate_portal(organization_id: str, distribution_id: int,
                      actor: str) -> DriverShiftPortalAccess:
    current = repository.portal_for_distribution(organization_id, distribution_id)
    period_end = repository.distribution_period_end(organization_id, distribution_id)
    generation = int(current["token_generation"]) + 1
    public_id, _, token_hash = _new_identity(generation)
    row = repository.regenerate_portal(
        organization_id, distribution_id, public_id, token_hash,
        _expires_at(period_end), actor,
    )
    return _access(row)


def validate_portal(token: str) -> DriverShiftPortalAvailability:
    if not token or len(token) > 256:
        raise DriverShiftPortalInvalidError("Accesso turni non disponibile.")
    repository.validate_token(_token_hash(token))
    return DriverShiftPortalAvailability()
