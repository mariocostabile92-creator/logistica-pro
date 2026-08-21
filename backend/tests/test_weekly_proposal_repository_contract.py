from datetime import date, datetime, timezone
from inspect import getsource, signature

import pytest

from app.domain.core_language import OperationalUnit
from app.domain.workforce_auto_planning import (
    ComposedWeeklyWorkforceProposal,
    WeeklyPlanningInputSnapshot,
    WeeklyWorkforceProposal,
    WeeklyWorkforceProposalOrganizationMismatchError,
    WeeklyWorkforceProposalRepository,
    WeeklyWorkforceProposalRevisionAlreadyExistsError,
    WeeklyWorkforceProposalRevisionNotFoundError,
    WeeklyWorkforceProposalSnapshotMismatchError,
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
        snapshot: WeeklyPlanningInputSnapshot,
        aggregate: ComposedWeeklyWorkforceProposal,
    ) -> ComposedWeeklyWorkforceProposal:
        organization_id = self._organization_id(organization_id)
        repository_module.validate_weekly_workforce_proposal_save_contract(
            organization_id=organization_id,
            snapshot=snapshot,
            aggregate=aggregate,
        )
        proposal = aggregate.proposal
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


def _snapshot_for(
    aggregate: ComposedWeeklyWorkforceProposal,
) -> WeeklyPlanningInputSnapshot:
    proposal = aggregate.proposal
    return WeeklyPlanningInputSnapshot(
        snapshot_id=proposal.input_snapshot_id,
        organization_id=proposal.organization_id,
        period_start=proposal.period_start,
        period_end=proposal.period_end,
        operational_unit=proposal.operational_unit,
        demands=(),
        workforce_candidates=(),
        policy_set_identifier=proposal.policy_set_identifier,
        policy_set_version=proposal.policy_set_version,
        created_at=datetime(2026, 8, 20, tzinfo=timezone.utc),
        fingerprint=proposal.input_fingerprint,
    )


def _save(
    repository: InMemoryWeeklyWorkforceProposalRepository,
    aggregate: ComposedWeeklyWorkforceProposal,
    *,
    organization_id: str | None = None,
    snapshot: WeeklyPlanningInputSnapshot | None = None,
) -> ComposedWeeklyWorkforceProposal:
    return repository.save_revision(
        organization_id=(
            aggregate.proposal.organization_id
            if organization_id is None
            else organization_id
        ),
        snapshot=snapshot or _snapshot_for(aggregate),
        aggregate=aggregate,
    )


def test_repository_protocol_is_structurally_implementable() -> None:
    assert isinstance(
        InMemoryWeeklyWorkforceProposalRepository(),
        WeeklyWorkforceProposalRepository,
    )


def test_save_contract_requires_authoritative_snapshot() -> None:
    parameters = signature(
        WeeklyWorkforceProposalRepository.save_revision
    ).parameters

    assert tuple(parameters) == (
        "self",
        "organization_id",
        "snapshot",
        "aggregate",
    )
    assert parameters["organization_id"].kind.name == "KEYWORD_ONLY"
    assert parameters["snapshot"].kind.name == "KEYWORD_ONLY"
    assert parameters["aggregate"].kind.name == "KEYWORD_ONLY"


def test_snapshot_mismatch_error_belongs_to_repository_error_hierarchy() -> None:
    assert issubclass(
        WeeklyWorkforceProposalSnapshotMismatchError,
        repository_module.WeeklyWorkforceProposalRepositoryError,
    )


def test_save_and_get_exact_revision_without_mutating_aggregate() -> None:
    repository = InMemoryWeeklyWorkforceProposalRepository()
    aggregate = _aggregate()
    before = aggregate.model_dump(mode="json")

    snapshot = _snapshot_for(aggregate)
    snapshot_before = snapshot.model_dump(mode="json")
    saved = repository.save_revision(
        organization_id="organization-one",
        snapshot=snapshot,
        aggregate=aggregate,
    )
    loaded = repository.get_revision(
        organization_id="organization-one",
        proposal_id="proposal-one",
        version=1,
    )

    assert saved is aggregate
    assert loaded is aggregate
    assert aggregate.model_dump(mode="json") == before
    assert snapshot.model_dump(mode="json") == snapshot_before


def test_revisions_are_listed_by_increasing_version() -> None:
    repository = InMemoryWeeklyWorkforceProposalRepository()
    for version in (3, 1, 2):
        _save(repository, _aggregate(version=version))

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
        _save(repository, aggregate)

    latest = repository.latest_revision(
        organization_id="organization-one", proposal_id="proposal-one"
    )

    assert latest.proposal.version == 3
    assert latest.proposal.status is WeeklyWorkforceProposalStatus.DRAFT


def test_duplicate_revision_is_rejected_without_upsert() -> None:
    repository = InMemoryWeeklyWorkforceProposalRepository()
    original = _aggregate()
    _save(repository, original)

    with pytest.raises(WeeklyWorkforceProposalRevisionAlreadyExistsError):
        _save(
            repository,
            _aggregate(status=WeeklyWorkforceProposalStatus.APPROVED),
        )

    assert repository.get_revision(
        organization_id="organization-one",
        proposal_id="proposal-one",
        version=1,
    ) is original


def test_missing_revision_and_proposal_raise_typed_not_found() -> None:
    repository = InMemoryWeeklyWorkforceProposalRepository()
    _save(repository, _aggregate())

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


def test_save_rejects_snapshot_organization_mismatch() -> None:
    repository = InMemoryWeeklyWorkforceProposalRepository()
    aggregate = _aggregate(organization_id="organization-one")
    snapshot = _snapshot_for(aggregate).model_copy(
        update={"organization_id": "organization-two"}
    )

    with pytest.raises(WeeklyWorkforceProposalOrganizationMismatchError):
        _save(
            repository,
            aggregate,
            snapshot=snapshot,
        )


def test_save_rejects_aggregate_organization_mismatch() -> None:
    repository = InMemoryWeeklyWorkforceProposalRepository()
    aggregate = _aggregate(organization_id="organization-one")
    snapshot = _snapshot_for(aggregate).model_copy(
        update={"organization_id": "organization-two"}
    )

    with pytest.raises(WeeklyWorkforceProposalOrganizationMismatchError):
        _save(
            repository,
            aggregate,
            organization_id="organization-two",
            snapshot=snapshot,
        )


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("snapshot_id", "other-snapshot"),
        ("fingerprint", "other-fingerprint"),
        ("period_start", date(2026, 8, 23)),
        ("period_end", date(2026, 8, 31)),
        (
            "operational_unit",
            OperationalUnit(external_identifier="unit-south"),
        ),
        ("policy_set_identifier", "other-policy-set"),
        ("policy_set_version", "2"),
    ),
)
def test_save_rejects_snapshot_proposal_consistency_mismatch(
    field: str,
    value: object,
) -> None:
    repository = InMemoryWeeklyWorkforceProposalRepository()
    aggregate = _aggregate()
    snapshot = _snapshot_for(aggregate).model_copy(update={field: value})

    with pytest.raises(WeeklyWorkforceProposalSnapshotMismatchError):
        _save(repository, aggregate, snapshot=snapshot)


def test_organizations_are_strictly_isolated_for_same_proposal_id() -> None:
    repository = InMemoryWeeklyWorkforceProposalRepository()
    first = _aggregate(organization_id="organization-one")
    second = _aggregate(organization_id="organization-two")
    _save(repository, first)
    _save(repository, second)

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
        _save(repository, _aggregate(version=version))

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


def test_read_operation_signatures_remain_unchanged() -> None:
    assert tuple(
        signature(WeeklyWorkforceProposalRepository.get_revision).parameters
    ) == ("self", "organization_id", "proposal_id", "version")
    assert tuple(
        signature(WeeklyWorkforceProposalRepository.list_revisions).parameters
    ) == ("self", "organization_id", "proposal_id")
    assert tuple(
        signature(WeeklyWorkforceProposalRepository.latest_revision).parameters
    ) == ("self", "organization_id", "proposal_id")


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
