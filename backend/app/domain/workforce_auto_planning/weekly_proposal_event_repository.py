from typing import Protocol, runtime_checkable

from app.domain.workforce_auto_planning.weekly_proposal_event import (
    WeeklyWorkforceProposalEvent,
)


class WeeklyWorkforceProposalEventRepositoryError(RuntimeError):
    pass


class WeeklyWorkforceProposalEventOrganizationMismatchError(
    WeeklyWorkforceProposalEventRepositoryError
):
    pass


class WeeklyWorkforceProposalEventAlreadyExistsError(
    WeeklyWorkforceProposalEventRepositoryError
):
    pass


def validate_weekly_workforce_proposal_event_scope(
    *,
    organization_id: str,
    event: WeeklyWorkforceProposalEvent,
) -> None:
    if (
        not isinstance(organization_id, str)
        or not organization_id.strip()
        or organization_id != event.organization_id
    ):
        raise WeeklyWorkforceProposalEventOrganizationMismatchError(
            "event organization does not match repository scope"
        )


@runtime_checkable
class WeeklyWorkforceProposalEventRepository(Protocol):
    def append_event(
        self,
        *,
        organization_id: str,
        event: WeeklyWorkforceProposalEvent,
    ) -> WeeklyWorkforceProposalEvent:
        """Append one immutable organization-scoped proposal event."""
        ...
