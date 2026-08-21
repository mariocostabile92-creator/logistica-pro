from typing import Protocol, runtime_checkable

from app.domain.workforce_auto_planning.weekly_proposal_composer import (
    ComposedWeeklyWorkforceProposal,
)


class WeeklyWorkforceProposalRepositoryError(RuntimeError):
    pass


class WeeklyWorkforceProposalRevisionNotFoundError(
    WeeklyWorkforceProposalRepositoryError
):
    pass


class WeeklyWorkforceProposalRevisionAlreadyExistsError(
    WeeklyWorkforceProposalRepositoryError
):
    pass


class WeeklyWorkforceProposalOrganizationMismatchError(
    WeeklyWorkforceProposalRepositoryError
):
    pass


@runtime_checkable
class WeeklyWorkforceProposalRepository(Protocol):
    def save_revision(
        self,
        *,
        organization_id: str,
        aggregate: ComposedWeeklyWorkforceProposal,
    ) -> ComposedWeeklyWorkforceProposal:
        """Persist one complete, new proposal revision without an upsert."""
        ...

    def get_revision(
        self,
        *,
        organization_id: str,
        proposal_id: str,
        version: int,
    ) -> ComposedWeeklyWorkforceProposal:
        """Return one exact organization-scoped proposal revision."""
        ...

    def list_revisions(
        self,
        *,
        organization_id: str,
        proposal_id: str,
    ) -> tuple[ComposedWeeklyWorkforceProposal, ...]:
        """Return all revisions ordered by increasing version."""
        ...

    def latest_revision(
        self,
        *,
        organization_id: str,
        proposal_id: str,
    ) -> ComposedWeeklyWorkforceProposal:
        """Return max(version), without current, active, or approval semantics."""
        ...
