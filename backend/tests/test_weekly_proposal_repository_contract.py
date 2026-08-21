from datetime import date, datetime, timezone
from inspect import getsource

import pytest

from app.domain.core_language import OperationalUnit
from app.domain.workforce_auto_planning import (
    ComposedWeeklyWorkforceProposal,
    WeeklyWorkforceProposal,
    WeeklyWorkforceProposalOrganizationMismatchError,
    WeeklyWorkforceProposalRepository,
    WeeklyWorkforceProposalRevisionAlreadyExistsError,
    WeeklyWorkforceProposalRevisionNotFoundError,
    WeeklyWorkforceProposalStatus,
)
from app.domain.workforce_auto_planning import (
    weekly_proposal_repository as repository_module,
)


class InMemoryWeeklyWorkforceProposalRepository:
    def __init__(self) -> None:
        self._revisions: dict[
            tuple[str, str, int], ComposedWeeklyWorkforceProposal
        ] = {}

    @staticmethod
    def _organization_id(value: str) -> str:
        if not isinstance(value, str) or not value.strip():
            raise ValueError("organization_id is required")
        return value

    @staticmethod
    def _proposal_id(value: str) -> str:
        if not isinstance(value, str) or not value.strip():
            raise ValueError("proposal_id is required")
        return value

    @staticmethod
    def _version(value: int) -> int:
        if type(value) is not int or value <= 0:
            raise ValueError("version must be a strict positive integer")
        return value

    def save_revision(
        self,
        *,
        organization_id: str,
        aggregate: ComposedWeeklyWorkforceProposal,
    ) -> ComposedWeeklyWorkforceProposal:
        organization_id = self._organization_id(organization_id)
        proposal = aggregate.proposal
        if proposal.organization_id != organization_id:
            raise WeeklyWorkforceProposalOrganizationMismatchError(
                "aggregate organization does not match repository scope"
            )
        key = (
            organization_id,
            self._proposal_id(proposal.proposal_id),
            self._version(proposal.version),
        )
        if key in self._revisions:
            raise WeeklyWorkforceProposalRevisionAlreadyExistsError(
                "proposal revision already exists"
            )
        self._revisions[key] = aggregate
        return aggregate

    def get_revision(
        self,
        *,
        organization_id: str,
        proposal_id: str,
        version: int,
    ) -> ComposedWeeklyWorkforceProposal:
        key = (
            self._organization_id(organization_id),
            self._proposal_id(proposal_id),
            self._version(version),
        )
        try:
            return self._revisions[key]
        except KeyError as exc:
            raise WeeklyWorkforceProposalRevisionNotFoundError(
                "proposal revision not found"
            ) from exc

    def list_revisions(
        self,
        *,
        organization_id: str,
        proposal_id: str,
    ) -> tuple[ComposedWeeklyWorkforceProposal, ...]:
        organization_id = self._organization_id(organization_id)
        proposal_id = self._proposal_id(proposal_id)
        revisions = tuple(
            aggregate
            for (stored_organization, stored_proposal, _), aggregate in sorted(
                self._revisions.items(), key=lambda item: item[0][2]
            )
            if stored_organization == organization_id
            and stored_proposal == proposal_id
        )
        if not revisions:
            raise WeeklyWorkforceProposalRevisionNotFoundError(
                "proposal revisions not found"
            )
        return revisions

    def latest_revision(
        self,
        *,
        organization_id: str,
        proposal_id: str,
    ) -> ComposedWeeklyWorkforceProposal:
        return self.list_revisions(
            organization_id=organization_id,
            proposal_id=proposal_id,
        )[-1]


def _aggregate(
    *,
    organization_id: str = "organization-one",
    proposal_id: str = "proposal-one",
    version: int = 1,
    status: WeeklyWorkforceProposalStatus = (
        WeeklyWorkforceProposalStatus.GENERATED
    ),
) -> ComposedWeeklyWorkforceProposal:
    proposal = WeeklyWorkforceProposal(
        proposal_id=proposal_id,
        organization_id=organization_id,
        period_start=date(2026, 8, 24),
        period_end=date(2026, 8, 30),
        operational_unit=OperationalUnit(external_identifier="unit-north"),
        version=version,
        input_snapshot_id=f"snapshot-{organization_id}-{version}",
        input_fingerprint=f"fingerprint-{organization_id}-{version}",
        policy_set_identifier="policy-set",
        policy_set_version="1",
        status=status,
        created_at=datetime(2026, 8, 21, tzinfo=timezone.utc),
    )
    return ComposedWeeklyWorkforceProposal(
        proposal=proposal,
        assignments=(),
        coverage_gaps=(),
        eligibility_decisions=(),
        preference_sets=(),
        ranked_candidates=(),
    )


def test_repository_protocol_is_structurally_implementable() -> None:
    assert isinstance(
        InMemoryWeeklyWorkforceProposalRepository(),
        WeeklyWorkforceProposalRepository,
    )


def test_save_and_get_exact_revision_without_mutating_aggregate() -> None:
    repository = InMemoryWeeklyWorkforceProposalRepository()
    aggregate = _aggregate()
    before = aggregate.model_dump(mode="json")

    saved = repository.save_revision(
        organization_id="organization-one", aggregate=aggregate
    )
    loaded = repository.get_revision(
        organization_id="organization-one",
        proposal_id="proposal-one",
        version=1,
    )

    assert saved is aggregate
    assert loaded is aggregate
    assert aggregate.model_dump(mode="json") == before


def test_revisions_are_listed_by_increasing_version() -> None:
    repository = InMemoryWeeklyWorkforceProposalRepository()
    for version in (3, 1, 2):
        repository.save_revision(
            organization_id="organization-one",
            aggregate=_aggregate(version=version),
        )

    revisions = repository.list_revisions(
        organization_id="organization-one", proposal_id="proposal-one"
    )

    assert isinstance(revisions, tuple)
    assert tuple(item.proposal.version for item in revisions) == (1, 2, 3)
    with pytest.raises(TypeError):
        revisions[0] = revisions[1]


def test_latest_revision_returns_max_version_without_status_semantics() -> None:
    repository = InMemoryWeeklyWorkforceProposalRepository()
    revisions = (
        _aggregate(version=1, status=WeeklyWorkforceProposalStatus.APPROVED),
        _aggregate(version=2, status=WeeklyWorkforceProposalStatus.SUPERSEDED),
        _aggregate(version=3, status=WeeklyWorkforceProposalStatus.DRAFT),
    )
    for aggregate in revisions:
        repository.save_revision(
            organization_id="organization-one", aggregate=aggregate
        )

    latest = repository.latest_revision(
        organization_id="organization-one", proposal_id="proposal-one"
    )

    assert latest.proposal.version == 3
    assert latest.proposal.status is WeeklyWorkforceProposalStatus.DRAFT


def test_duplicate_revision_is_rejected_without_upsert() -> None:
    repository = InMemoryWeeklyWorkforceProposalRepository()
    original = _aggregate()
    repository.save_revision(
        organization_id="organization-one", aggregate=original
    )

    with pytest.raises(WeeklyWorkforceProposalRevisionAlreadyExistsError):
        repository.save_revision(
            organization_id="organization-one",
            aggregate=_aggregate(status=WeeklyWorkforceProposalStatus.APPROVED),
        )

    assert repository.get_revision(
        organization_id="organization-one",
        proposal_id="proposal-one",
        version=1,
    ) is original


def test_missing_revision_and_proposal_raise_typed_not_found() -> None:
    repository = InMemoryWeeklyWorkforceProposalRepository()
    repository.save_revision(
        organization_id="organization-one", aggregate=_aggregate()
    )

    with pytest.raises(WeeklyWorkforceProposalRevisionNotFoundError):
        repository.get_revision(
            organization_id="organization-one",
            proposal_id="proposal-one",
            version=2,
        )
    with pytest.raises(WeeklyWorkforceProposalRevisionNotFoundError):
        repository.list_revisions(
            organization_id="organization-one", proposal_id="missing-proposal"
        )
    with pytest.raises(WeeklyWorkforceProposalRevisionNotFoundError):
        repository.latest_revision(
            organization_id="organization-one", proposal_id="missing-proposal"
        )


def test_save_rejects_organization_mismatch() -> None:
    repository = InMemoryWeeklyWorkforceProposalRepository()

    with pytest.raises(WeeklyWorkforceProposalOrganizationMismatchError):
        repository.save_revision(
            organization_id="organization-two",
            aggregate=_aggregate(organization_id="organization-one"),
        )


def test_organizations_are_strictly_isolated_for_same_proposal_id() -> None:
    repository = InMemoryWeeklyWorkforceProposalRepository()
    first = _aggregate(organization_id="organization-one")
    second = _aggregate(organization_id="organization-two")
    repository.save_revision(organization_id="organization-one", aggregate=first)
    repository.save_revision(organization_id="organization-two", aggregate=second)

    assert repository.get_revision(
        organization_id="organization-one",
        proposal_id="proposal-one",
        version=1,
    ) is first
    assert repository.get_revision(
        organization_id="organization-two",
        proposal_id="proposal-one",
        version=1,
    ) is second
    with pytest.raises(WeeklyWorkforceProposalRevisionNotFoundError):
        repository.get_revision(
            organization_id="organization-three",
            proposal_id="proposal-one",
            version=1,
        )


def test_same_proposal_id_accepts_multiple_versions() -> None:
    repository = InMemoryWeeklyWorkforceProposalRepository()
    for version in (1, 2, 3):
        repository.save_revision(
            organization_id="organization-one",
            aggregate=_aggregate(version=version),
        )

    assert tuple(
        item.proposal.version
        for item in repository.list_revisions(
            organization_id="organization-one", proposal_id="proposal-one"
        )
    ) == (1, 2, 3)


@pytest.mark.parametrize("version", (0, -1, True))
def test_invalid_version_is_rejected(version: object) -> None:
    repository = InMemoryWeeklyWorkforceProposalRepository()

    with pytest.raises(ValueError):
        repository.get_revision(
            organization_id="organization-one",
            proposal_id="proposal-one",
            version=version,
        )


@pytest.mark.parametrize(
    ("organization_id", "proposal_id"),
    (("", "proposal-one"), ("   ", "proposal-one"), ("organization-one", ""),
     ("organization-one", "   ")),
)
def test_blank_scope_identifiers_are_rejected(
    organization_id: str, proposal_id: str
) -> None:
    repository = InMemoryWeeklyWorkforceProposalRepository()

    with pytest.raises(ValueError):
        repository.get_revision(
            organization_id=organization_id,
            proposal_id=proposal_id,
            version=1,
        )


def test_port_contains_only_minimal_revision_operations() -> None:
    public_methods = {
        name
        for name, value in WeeklyWorkforceProposalRepository.__dict__.items()
        if callable(value) and not name.startswith("_")
    }

    assert public_methods == {
        "save_revision",
        "get_revision",
        "list_revisions",
        "latest_revision",
    }


def test_core_port_has_no_currentness_or_persistence_dependencies() -> None:
    source = getsource(repository_module).casefold()
    forbidden = (
        "is_current",
        "list_current",
        "list_by_week",
        "list_by_unit",
        "list_approved",
        "sqlalchemy",
        "sqlite",
        "psycopg",
        "db_session",
        "fastapi",
        "plugins.workforce",
    )

    assert all(term not in source for term in forbidden)
