from datetime import date

from app.plugins.workforce.domain.errors import WorkforceValidationError
from app.plugins.workforce.infrastructure import week_copy_repository


def _target_week_start(value: str) -> str:
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise WorkforceValidationError("La settimana target non e valida.") from exc
    if parsed.isoweekday() != 1:
        raise WorkforceValidationError("La settimana target deve iniziare di lunedi.")
    return parsed.isoformat()


def preview(member_id: int, target_week_start: str, organization_id: str):
    return week_copy_repository.preview(
        member_id,
        _target_week_start(target_week_start),
        organization_id,
    )


def apply(
    member_id: int,
    target_week_start: str,
    expected_fingerprint: str,
    actor: str,
    organization_id: str,
):
    return week_copy_repository.apply(
        member_id,
        _target_week_start(target_week_start),
        expected_fingerprint,
        actor,
        organization_id,
    )
