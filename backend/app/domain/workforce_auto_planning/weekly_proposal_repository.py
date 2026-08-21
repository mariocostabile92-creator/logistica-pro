from typing import Protocol, runtime_checkable

from app.domain.workforce_auto_planning.weekly_proposal_composer import (
    ComposedWeeklyWorkforceProposal,
)
from app.domain.workforce_auto_planning.weekly_planning_input_snapshot import (
    WeeklyPlanningInputSnapshot,
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


class WeeklyWorkforceProposalSnapshotMismatchError(
    WeeklyWorkforceProposalRepositoryError
):
    pass


def validate_weekly_workforce_proposal_save_contract(
    *,
    organization_id: str,
    snapshot: WeeklyPlanningInputSnapshot,
    aggregate: ComposedWeeklyWorkforceProposal,
) -> None:
    proposal = aggregate.proposal
    if (
        snapshot.organization_id != organization_id
        or proposal.organization_id != organization_id
    ):
        raise WeeklyWorkforceProposalOrganizationMismatchError(
            "snapshot and aggregate organizations must match repository scope"
        )

    consistency_checks = (
        (
            snapshot.snapshot_id == proposal.input_snapshot_id,
            "snapshot_id does not match proposal input_snapshot_id",
        ),
        (
            snapshot.fingerprint == proposal.input_fingerprint,
            "snapshot fingerprint does not match proposal input fingerprint",
        ),
        (
            snapshot.period_start == proposal.period_start,
            "snapshot period_start does not match proposal period_start",
        ),
        (
            snapshot.period_end == proposal.period_end,
            "snapshot period_end does not match proposal period_end",
        ),
        (
            snapshot.operational_unit.external_identifier
            == proposal.operational_unit.external_identifier,
            "snapshot operational unit does not match proposal operational unit",
        ),
        (
            snapshot.policy_set_identifier
            == proposal.policy_set_identifier,
            "snapshot policy identifier does not match proposal policy identifier",
        ),
        (
            snapshot.policy_set_version == proposal.policy_set_version,
            "snapshot policy version does not match proposal policy version",
        ),
    )
    for is_consistent, message in consistency_checks:
        if not is_consistent:
            raise WeeklyWorkforceProposalSnapshotMismatchError(message)


@runtime_checkable
class WeeklyWorkforceProposalRepository(Protocol):
    def save_revision(
        self,
        *,
        organization_id: str,
        snapshot: WeeklyPlanningInputSnapshot,
        aggregate: ComposedWeeklyWorkforceProposal,
    ) -> ComposedWeeklyWorkforceProposal:
        """Persist a new revision with its authoritative immutable snapshot."""
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
