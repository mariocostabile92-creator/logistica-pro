import hashlib
import hmac
import uuid
from datetime import date, timedelta

from app.core.config import SETTINGS
from app.plugins.workforce.domain.driver_shift_distribution import (
    DriverShiftDistributionError,
    DriverShiftDistributionReadModel,
    DriverShiftPersonalAccessNotFoundError,
    DriverShiftRecipientAccessLink,
    PersonalDriverShiftView,
)
from app.plugins.workforce.infrastructure import driver_shift_distribution_repository as repository


ACCESS_GRACE_DAYS = 7


def _key() -> bytes:
    return (SETTINGS.secret_key or "operations-engine-development-driver-shifts").encode("utf-8")


def _token(public_id: str, generation: int) -> str:
    payload = f"{public_id}.{generation}"
    signature = hmac.new(_key(), payload.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"{payload}.{signature}"


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _expires_at(period_end: str) -> str:
    expiry = date.fromisoformat(period_end) + timedelta(days=ACCESS_GRACE_DAYS)
    return f"{expiry.isoformat()}T23:59:59Z"


def _access_link(recipient: dict) -> DriverShiftRecipientAccessLink:
    if recipient.get("access_revoked_at") or recipient.get("distribution_status") == "SUPERSEDED":
        raise DriverShiftDistributionError("Accesso revocato: rigeneralo prima di condividerlo.")
    token = _token(str(recipient["public_id"]), int(recipient["access_generation"]))
    if not hmac.compare_digest(_token_hash(token), str(recipient["access_token_hash"])):
        raise DriverShiftDistributionError("Accesso personale non coerente: rigeneralo.")
    return DriverShiftRecipientAccessLink(
        recipient_id=int(recipient["id"]),
        access_url=f"{SETTINGS.base_url}/app/driver-shifts/#token={token}",
        expires_at=str(recipient["access_expires_at"]),
    )


def prepare_distribution(organization_id: str, planning_id: int,
                         actor: str) -> DriverShiftDistributionReadModel:
    planning, candidates = repository.published_recipient_candidates(
        organization_id, planning_id,
    )
    expires_at = _expires_at(str(planning["period_end"]))
    recipients = []
    for candidate in candidates:
        public_id = str(uuid.uuid4())
        generation = 1
        token = _token(public_id, generation)
        recipients.append({
            "public_id": public_id,
            "workforce_member_id": int(candidate["workforce_member_id"]),
            "access_generation": generation,
            "access_token_hash": _token_hash(token),
            "access_expires_at": expires_at,
        })
    return repository.prepare_distribution(
        organization_id, planning, recipients, actor,
    )


def distribution_for_planning(organization_id: str,
                              planning_id: int) -> DriverShiftDistributionReadModel:
    return repository.distribution_for_planning(organization_id, planning_id)


def recipient_access_link(organization_id: str, distribution_id: int,
                          recipient_id: int) -> DriverShiftRecipientAccessLink:
    recipient = repository.recipient_access(
        organization_id, distribution_id, recipient_id,
    )
    return _access_link(recipient)


def revoke_recipient_access(organization_id: str, distribution_id: int,
                            recipient_id: int, actor: str) -> DriverShiftDistributionReadModel:
    return repository.revoke_recipient(
        organization_id, distribution_id, recipient_id, actor,
    )


def regenerate_recipient_access(organization_id: str, distribution_id: int,
                                recipient_id: int, actor: str) -> DriverShiftRecipientAccessLink:
    current = repository.recipient_access(
        organization_id, distribution_id, recipient_id,
    )
    if current["distribution_status"] == "SUPERSEDED":
        raise DriverShiftDistributionError("Una distribuzione superata non può generare nuovi accessi.")
    generation = int(current["access_generation"]) + 1
    token = _token(str(current["public_id"]), generation)
    updated = repository.regenerate_recipient(
        organization_id, distribution_id, recipient_id, generation,
        _token_hash(token), str(current["access_expires_at"]), actor,
    )
    updated["distribution_status"] = current["distribution_status"]
    return _access_link(updated)


def personal_shifts(token: str) -> PersonalDriverShiftView:
    if not token or len(token) > 256:
        raise DriverShiftPersonalAccessNotFoundError("Accesso turni non disponibile.")
    return repository.personal_view(_token_hash(token))


def acknowledge(token: str) -> PersonalDriverShiftView:
    if not token or len(token) > 256:
        raise DriverShiftPersonalAccessNotFoundError("Accesso turni non disponibile.")
    return repository.personal_view(_token_hash(token), acknowledge=True)
