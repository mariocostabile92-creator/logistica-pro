from app.plugins.fleet.damage.domain.driver_attribution import (
    CanonicalDamageDriverAttribution,
    DamageDriverAttributionRejected,
    DamageDriverAttributionSource,
)
from app.plugins.fleet.damage.infrastructure import repository
from app.plugins.workforce.domain.driver_identity import (
    DriverIdentityResolution,
    DriverIdentityResolutionStatus,
)
from app.plugins.workforce.domain.models import WorkforceMember


class DamageDriverAttributionError(ValueError):
    pass


class DamageDriverAttributionInvalid(DamageDriverAttributionError):
    pass


class DamageDriverAttributionNotFound(DamageDriverAttributionError):
    pass


class DamageDriverAttributionOrganizationMismatch(DamageDriverAttributionError):
    pass


def _command(
    *,
    workforce_member_id: int,
    source: str,
    actor: str,
    reason: str | None = None,
) -> CanonicalDamageDriverAttribution:
    try:
        return CanonicalDamageDriverAttribution(
            workforce_member_id=workforce_member_id,
            source=source,
            attributed_by=actor,
            reason=reason,
        )
    except (TypeError, ValueError) as exc:
        raise DamageDriverAttributionInvalid(
            "Attribuzione driver canonica non valida."
        ) from exc


def from_identity_resolution(
    resolution: DriverIdentityResolution,
    *,
    actor: str,
    reason: str | None = None,
) -> CanonicalDamageDriverAttribution:
    if (
        not isinstance(resolution, DriverIdentityResolution)
        or resolution.status is not DriverIdentityResolutionStatus.MATCH
        or not resolution.matched
        or resolution.workforce_member_id is None
        or resolution.source not in {
            DamageDriverAttributionSource.JOURNAL.value,
            DamageDriverAttributionSource.PLANNING.value,
        }
    ):
        raise DamageDriverAttributionInvalid(
            "Il resolver non ha restituito un Workforce member canonico."
        )
    return _command(
        workforce_member_id=resolution.workforce_member_id,
        source=resolution.source,
        actor=actor,
        reason=reason,
    )


def attribute_driver(
    case_id: int,
    member: WorkforceMember,
    *,
    source: str,
    actor: str,
    reason: str | None = None,
):
    command = from_workforce_member(
        member,
        source=source,
        actor=actor,
        reason=reason,
    )
    try:
        updated = repository.attribute_driver(case_id, command)
    except DamageDriverAttributionRejected as exc:
        raise DamageDriverAttributionOrganizationMismatch(str(exc)) from exc
    if not updated:
        raise DamageDriverAttributionNotFound("Pratica danno non trovata.")
    return updated


def from_workforce_member(
    member: WorkforceMember,
    *,
    source: str,
    actor: str,
    reason: str | None = None,
) -> CanonicalDamageDriverAttribution:
    if not isinstance(member, WorkforceMember):
        raise DamageDriverAttributionInvalid(
            "L'attribuzione definitiva richiede un Workforce member canonico."
        )
    return _command(
        workforce_member_id=member.workforce_member_id,
        source=source,
        actor=actor,
        reason=reason,
    )
