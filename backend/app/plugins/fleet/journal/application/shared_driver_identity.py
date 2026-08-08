from dataclasses import dataclass
from enum import Enum

from app.plugins.workforce.infrastructure import read_repository


class SharedDriverIdentityStatus(str, Enum):
    MATCH = "match"
    NOT_FOUND = "not_found"
    AMBIGUOUS = "ambiguous"


@dataclass(frozen=True)
class SharedDriverIdentity:
    status: SharedDriverIdentityStatus
    persisted_identifier: str
    workforce_member_id: int | None = None

    @property
    def matched(self) -> bool:
        return self.status is SharedDriverIdentityStatus.MATCH


def resolve_shared_driver_identity(
    organization_id: str,
    display_name: str,
) -> SharedDriverIdentity:
    """Resolve one exact, organization-scoped Workforce display name.

    The display name is retained only as the legacy fallback. It is never
    transformed into, or treated as, a canonical Workforce identifier.
    """
    candidates = read_repository.find_members_by_display_name(
        organization_id,
        display_name,
    )
    if not candidates:
        return SharedDriverIdentity(
            status=SharedDriverIdentityStatus.NOT_FOUND,
            persisted_identifier=display_name,
        )
    if len(candidates) != 1:
        return SharedDriverIdentity(
            status=SharedDriverIdentityStatus.AMBIGUOUS,
            persisted_identifier=display_name,
        )
    member = candidates[0]
    return SharedDriverIdentity(
        status=SharedDriverIdentityStatus.MATCH,
        persisted_identifier=member.external_identifier,
        workforce_member_id=member.workforce_member_id,
    )
