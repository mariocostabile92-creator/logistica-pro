import hashlib
import hmac
import uuid
import csv
import io
from datetime import date, timedelta

from app.core.config import SETTINGS
from app.plugins.workforce.domain.driver_shift_distribution import (
    DriverShiftDistributionError,
    DriverShiftDistributionPeriodError,
    DriverShiftDistributionReadModel,
    DriverShiftPersonalAccessNotFoundError,
    DriverShiftRecipientAccessLink,
    PersonalDriverShiftView,
    DriverShiftPreparedBatch,
    DriverShiftPreparedRecipient,
    DriverShiftDeliveryChannel,
)
from app.plugins.workforce.domain.driver_shift_contact import contact_readiness
from app.plugins.workforce.application.driver_shift_delivery_provider import MANUAL_SHARE_PROVIDER
from app.utils.date_utils import utc_now_iso
from app.plugins.workforce.infrastructure import driver_shift_distribution_repository as repository


ACCESS_GRACE_DAYS = 7
MESSAGE_TEMPLATE = (
    "Ciao {first_name}, sono disponibili i tuoi turni dal {period_start} "
    "al {period_end}. Puoi consultarli qui: {personal_url}"
)


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


def _distribution_period(
    planning: dict,
    period_start: str | None,
    period_end: str | None,
) -> tuple[str, str]:
    if (period_start is None) != (period_end is None):
        raise DriverShiftDistributionPeriodError(
            "Il periodo della distribuzione richiede data iniziale e finale."
        )
    start_value = period_start or str(planning["period_start"])
    end_value = period_end or str(planning["period_end"])
    try:
        start = date.fromisoformat(start_value)
        end = date.fromisoformat(end_value)
        planning_start = date.fromisoformat(str(planning["period_start"]))
        planning_end = date.fromisoformat(str(planning["period_end"]))
    except ValueError as exc:
        raise DriverShiftDistributionPeriodError(
            "Il periodo della distribuzione non è valido."
        ) from exc
    if end < start:
        raise DriverShiftDistributionPeriodError(
            "La data finale deve essere uguale o successiva alla data iniziale."
        )
    if start < planning_start or end > planning_end:
        raise DriverShiftDistributionPeriodError(
            "Il periodo della distribuzione deve essere contenuto nel planning ACTIVE."
        )
    return start.isoformat(), end.isoformat()


def prepare_distribution(
    organization_id: str,
    planning_id: int,
    actor: str,
    *,
    period_start: str | None = None,
    period_end: str | None = None,
) -> DriverShiftDistributionReadModel:
    planning = repository.active_planning(organization_id, planning_id)
    distribution_start, distribution_end = _distribution_period(
        planning, period_start, period_end,
    )
    candidates = repository.published_recipient_candidates(
        organization_id, planning, distribution_start, distribution_end,
    )
    expires_at = _expires_at(distribution_end)
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
        organization_id,
        planning,
        distribution_start,
        distribution_end,
        recipients,
        actor,
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


def prepare_batch(
    organization_id: str,
    distribution_id: int,
    recipient_ids: list[int] | None = None,
) -> DriverShiftPreparedBatch:
    distribution, candidates = repository.batch_recipient_candidates(
        organization_id, distribution_id, recipient_ids,
    )
    prepared: list[DriverShiftPreparedRecipient] = []
    excluded: list[int] = []
    now = utc_now_iso()
    for candidate in candidates:
        contact = contact_readiness(candidate.get("phone"), candidate.get("email"))
        eligible = (
            contact.readiness == "READY"
            and not candidate.get("access_revoked_at")
            and str(candidate["access_expires_at"]) >= now
        )
        if not eligible:
            excluded.append(int(candidate["id"]))
            continue
        link = _access_link(candidate)
        display_name = str(candidate["display_name"])
        first_name = (candidate.get("first_name") or display_name.split(maxsplit=1)[0]).strip()
        message = MESSAGE_TEMPLATE.format(
            first_name=first_name,
            period_start=distribution["period_start"],
            period_end=distribution["period_end"],
            personal_url=link.access_url,
        )
        prepared.append(DriverShiftPreparedRecipient(
            recipient_id=int(candidate["id"]),
            display_name=display_name,
            phone=contact.phone,
            email=contact.email,
            available_channels=list(contact.available_channels),
            personal_url=link.access_url,
            message=message,
        ))
    return DriverShiftPreparedBatch(
        distribution_id=distribution_id,
        period_start=str(distribution["period_start"]),
        period_end=str(distribution["period_end"]),
        requested_count=len(candidates),
        prepared_count=len(prepared),
        excluded_recipient_ids=excluded,
        recipients=prepared,
    )


def export_batch_csv(batch: DriverShiftPreparedBatch) -> str:
    def safe(value: str) -> str:
        return f"'{value}" if value[:1] in {"=", "+", "-", "@"} else value

    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=(
        "driver", "phone", "email", "personal_url", "message",
        "period_start", "period_end",
    ))
    writer.writeheader()
    for recipient in batch.recipients:
        writer.writerow({
            "driver": safe(recipient.display_name),
            "phone": safe(recipient.phone or ""),
            "email": safe(recipient.email or ""),
            "personal_url": safe(recipient.personal_url),
            "message": safe(recipient.message),
            "period_start": batch.period_start,
            "period_end": batch.period_end,
        })
    return output.getvalue()


def automatic_provider_sending_available() -> bool:
    return MANUAL_SHARE_PROVIDER.can_send(DriverShiftDeliveryChannel.MANUAL_SHARE)
