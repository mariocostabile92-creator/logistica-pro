from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path

import pytest

from app.domain.core_language import HumanResource, OperationalUnit, TimeWindow
from app.domain.workforce_auto_planning import (
    AssignedTimeSnapshot,
    AssignedTimeUnit,
    OperationalDemand,
    WeeklyPlanningInputSnapshot,
    WeeklyPlanningInputSnapshotComposer,
    WorkforceCandidateSnapshot,
    compute_weekly_planning_input_fingerprint,
)


START = date(2026, 8, 17)
END = date(2026, 8, 23)
UNIT = OperationalUnit(external_identifier="unit-north")
WINDOW = TimeWindow(external_identifier="open-window")
CREATED_AT = datetime(2026, 8, 16, 12, 0, tzinfo=timezone.utc)


def _demand() -> OperationalDemand:
    return OperationalDemand(
        organization_id="org-1",
        operational_unit=UNIT,
        date=START,
        time_window=WINDOW,
        capability_or_workload="parcel-delivery",
        base_quantity=5,
        target_quantity=6,
        source="generic-forecast",
    )


def _candidate() -> WorkforceCandidateSnapshot:
    return WorkforceCandidateSnapshot(
        organization_id="org-1",
        human_resource=HumanResource(
            external_identifier="member-1",
            capabilities=("parcel-delivery",),
        ),
        applicable_contract_reference="standard-contract",
        recent_consecutivity=2,
        already_assigned_minutes_or_hours=AssignedTimeSnapshot(
            value=Decimal("0"), unit=AssignedTimeUnit.MINUTES
        ),
    )


class RecordingDemandProvider:
    def __init__(self, demands):
        self.demands = demands
        self.calls = []

    def get_demands(self, **scope):
        self.calls.append(scope)
        return self.demands


class RecordingCandidateProvider:
    def __init__(self, candidates):
        self.candidates = candidates
        self.calls = []

    def get_candidates(self, **scope):
        self.calls.append(scope)
        return self.candidates


class FailingDemandProvider:
    def get_demands(self, **scope):
        raise LookupError("demand source unavailable")


class FailingCandidateProvider:
    def get_candidates(self, **scope):
        raise RuntimeError("candidate source unavailable")


def _compose(
    composer: WeeklyPlanningInputSnapshotComposer,
    *,
    snapshot_id: str = "snapshot-1",
    created_at: datetime = CREATED_AT,
) -> WeeklyPlanningInputSnapshot:
    return composer.compose(
        snapshot_id=snapshot_id,
        organization_id="org-1",
        period_start=START,
        period_end=END,
        operational_unit=UNIT,
        policy_set_identifier="weekly-policy",
        policy_set_version="1",
        created_at=created_at,
    )


def test_composer_uses_both_providers_with_the_complete_scope():
    demand_provider = RecordingDemandProvider((_demand(),))
    candidate_provider = RecordingCandidateProvider((_candidate(),))
    composer = WeeklyPlanningInputSnapshotComposer(
        demand_provider=demand_provider,
        candidate_provider=candidate_provider,
    )

    _compose(composer)

    expected_scope = {
        "organization_id": "org-1",
        "period_start": START,
        "period_end": END,
        "operational_unit": UNIT,
    }
    assert demand_provider.calls == [expected_scope]
    assert candidate_provider.calls == [expected_scope]


def test_provider_results_are_preserved_without_reinterpretation():
    demands = (_demand(),)
    candidates = (_candidate(),)
    composer = WeeklyPlanningInputSnapshotComposer(
        RecordingDemandProvider(demands),
        RecordingCandidateProvider(candidates),
    )

    snapshot = _compose(composer)

    assert snapshot.demands == demands
    assert snapshot.workforce_candidates == candidates


def test_composer_uses_the_existing_fingerprint_function():
    demands = (_demand(),)
    candidates = (_candidate(),)
    composer = WeeklyPlanningInputSnapshotComposer(
        RecordingDemandProvider(demands),
        RecordingCandidateProvider(candidates),
    )

    snapshot = _compose(composer)
    expected = compute_weekly_planning_input_fingerprint(
        organization_id="org-1",
        period_start=START,
        period_end=END,
        operational_unit=UNIT,
        demands=demands,
        workforce_candidates=candidates,
        policy_set_identifier="weekly-policy",
        policy_set_version="1",
    )

    assert snapshot.fingerprint == expected


def test_identity_and_creation_time_do_not_change_fingerprint():
    composer = WeeklyPlanningInputSnapshotComposer(
        RecordingDemandProvider((_demand(),)),
        RecordingCandidateProvider((_candidate(),)),
    )

    first = _compose(composer, snapshot_id="snapshot-a", created_at=CREATED_AT)
    second = _compose(
        composer,
        snapshot_id="snapshot-b",
        created_at=datetime(2026, 8, 17, 9, 0, tzinfo=timezone.utc),
    )

    assert first.fingerprint == second.fingerprint


def test_demand_provider_error_is_not_silenced():
    composer = WeeklyPlanningInputSnapshotComposer(
        FailingDemandProvider(),
        RecordingCandidateProvider((_candidate(),)),
    )

    with pytest.raises(LookupError, match="demand source unavailable"):
        _compose(composer)


def test_candidate_provider_error_is_not_silenced():
    composer = WeeklyPlanningInputSnapshotComposer(
        RecordingDemandProvider((_demand(),)),
        FailingCandidateProvider(),
    )

    with pytest.raises(RuntimeError, match="candidate source unavailable"):
        _compose(composer)


def test_composer_has_only_neutral_core_dependencies():
    composer_file = (
        Path(__file__).parents[1]
        / "app"
        / "domain"
        / "workforce_auto_planning"
        / "weekly_snapshot_composer.py"
    )
    source = composer_file.read_text(encoding="utf-8").lower()

    forbidden_terms = (
        "amazon",
        "dsp",
        "next_day",
        "same_day",
        "fleet",
        "vehicle",
        "plugins.workforce",
        "persistence",
        "repository",
        "database",
        "sqlalchemy",
        "fastapi",
    )
    assert all(term not in source for term in forbidden_terms)
