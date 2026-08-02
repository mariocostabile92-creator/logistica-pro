import uuid
from datetime import date

from app.plugins.workforce.domain.consecutivity import ConsecutivityOverride
from app.plugins.workforce.infrastructure import consecutivity_repository
from app.utils.date_utils import utc_now_iso


ALLOWED_TARGETS = {"callable", "limited", "not_callable"}


def create_override(
    organization_id: str,
    member_id: int,
    operation_date: str,
    valid_until: str,
    target_callability: str,
    reason: str,
    actor: str,
) -> ConsecutivityOverride:
    start = date.fromisoformat(operation_date)
    end = date.fromisoformat(valid_until)
    if end < start:
        raise ValueError("La validita dell'override non puo terminare prima della data iniziale.")
    if target_callability not in ALLOWED_TARGETS:
        raise ValueError("Stato override non supportato.")
    normalized_reason = reason.strip()
    if not normalized_reason:
        raise ValueError("La motivazione dell'override e obbligatoria.")
    return consecutivity_repository.insert_override({
        "id": str(uuid.uuid4()),
        "organization_id": organization_id,
        "workforce_member_id": member_id,
        "operation_date": start.isoformat(),
        "valid_until": end.isoformat(),
        "target_callability": target_callability,
        "reason": normalized_reason,
        "created_by": actor,
        "created_at": utc_now_iso(),
    })


def history(organization_id: str, member_id: int) -> list[ConsecutivityOverride]:
    return consecutivity_repository.override_history(organization_id, member_id)
