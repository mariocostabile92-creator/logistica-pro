from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

from app.domain.core_language import (
    HumanResource,
    OperationalUnit,
    ResourceAvailability,
    ResourceKind,
    TimeWindow,
)
from app.domain.workforce_auto_planning import (
    AssignedTimeSnapshot,
    AssignedTimeUnit,
    ConstraintEvidence,
    OperationalDemand,
    WeeklyPlanningInputSnapshot,
    WorkforceCandidateAvailabilitySnapshot,
    WorkforceCandidateSnapshot,
    compute_weekly_planning_input_fingerprint,
)


START = date(2026, 8, 17)
END = date(2026, 8, 23)
UNIT = OperationalUnit(external_identifier="unit-north", name="North hub")
WINDOW = TimeWindow(
    external_identifier="morning", starts_at="08:00", ends_at="16:00"
)


def _demand(day_offset: int, quantity: int = 8) -> OperationalDemand:
    return OperationalDemand(
        organization_id="org-1",
        operational_unit=UNIT,
        date=START + timedelta(days=day_offset),
        time_window=WINDOW,
        capability_or_workload="parcel-delivery",
        base_quantity=quantity,
        target_quantity=quantity,
        source="weekly-forecast",
    )


def _candidate(member_id: str, consecutive_days: int = 1):
    resource = HumanResource(
        external_identifier=member_id,
        display_name=f"Driver {member_id}",
        capabilities=("parcel-delivery", "fragile-handling"),
    )
    return WorkforceCandidateSnapshot(
        organization_id="org-1",
        human_resource=resource,
        availability=(
            WorkforceCandidateAvailabilitySnapshot(
                date=START,
                time_window=WINDOW,
                availability=ResourceAvailability(
                    resource_identifier=member_id,
                    resource_kind=ResourceKind.HUMAN_RESOURCE,
                    available=True,
                    observed_state="eligible",
                ),
            ),
        ),
        applicable_contract_reference="standard-contract",
        recent_consecutivity=consecutive_days,
        already_assigned_minutes_or_hours=AssignedTimeSnapshot(
            value=Decimal("0"), unit=AssignedTimeUnit.MINUTES
        ),
        evidence=(
            ConstraintEvidence(key="calendar", value="ready"),
            ConstraintEvidence(key="contract", value="active"),
        ),
    )


def _snapshot(
    *,
    snapshot_id: str = "snapshot-1",
    created_at: datetime | None = None,
    demands=None,
    candidates=None,
    policy_identifier: str = "weekly-policy",
    policy_version: str = "1",
    fingerprint: str = "not-used-by-computation",
):
    return WeeklyPlanningInputSnapshot(
        snapshot_id=snapshot_id,
        organization_id="org-1",
        period_start=START,
        period_end=END,
        operational_unit=UNIT,
        demands=demands or (_demand(0), _demand(1)),
        workforce_candidates=candidates or (
            _candidate("member-1"),
            _candidate("member-2"),
        ),
        policy_set_identifier=policy_identifier,
        policy_set_version=policy_version,
        created_at=created_at or datetime(2026, 8, 16, tzinfo=timezone.utc),
        fingerprint=fingerprint,
    )


def _fingerprint(snapshot: WeeklyPlanningInputSnapshot) -> str:
    return compute_weekly_planning_input_fingerprint(
        organization_id=snapshot.organization_id,
        period_start=snapshot.period_start,
        period_end=snapshot.period_end,
        operational_unit=snapshot.operational_unit,
        demands=snapshot.demands,
        workforce_candidates=snapshot.workforce_candidates,
        policy_set_identifier=snapshot.policy_set_identifier,
        policy_set_version=snapshot.policy_set_version,
    )


def test_same_logical_inputs_produce_same_fingerprint():
    assert _fingerprint(_snapshot()) == _fingerprint(_snapshot())


def test_demand_order_does_not_change_fingerprint():
    first = _snapshot(demands=(_demand(0), _demand(1)))
    reversed_order = _snapshot(demands=(_demand(1), _demand(0)))

    assert _fingerprint(first) == _fingerprint(reversed_order)


def test_candidate_order_does_not_change_fingerprint():
    first = _snapshot(candidates=(_candidate("member-1"), _candidate("member-2")))
    reversed_order = _snapshot(
        candidates=(_candidate("member-2"), _candidate("member-1"))
    )

    assert _fingerprint(first) == _fingerprint(reversed_order)


def test_nested_collection_order_does_not_change_fingerprint():
    first_candidate = _candidate("member-1")
    reversed_candidate = first_candidate.model_copy(
        update={
            "human_resource": first_candidate.human_resource.model_copy(
                update={
                    "capabilities": tuple(
                        reversed(first_candidate.human_resource.capabilities)
                    )
                }
            ),
            "evidence": tuple(reversed(first_candidate.evidence)),
        }
    )

    assert _fingerprint(_snapshot(candidates=(first_candidate,))) == _fingerprint(
        _snapshot(candidates=(reversed_candidate,))
    )


def test_changed_demand_changes_fingerprint():
    assert _fingerprint(_snapshot(demands=(_demand(0, 8),))) != _fingerprint(
        _snapshot(demands=(_demand(0, 9),))
    )


def test_changed_candidate_changes_fingerprint():
    assert _fingerprint(
        _snapshot(candidates=(_candidate("member-1", consecutive_days=1),))
    ) != _fingerprint(
        _snapshot(candidates=(_candidate("member-1", consecutive_days=2),))
    )


def test_changed_policy_identifier_changes_fingerprint():
    assert _fingerprint(_snapshot(policy_identifier="policy-a")) != _fingerprint(
        _snapshot(policy_identifier="policy-b")
    )


def test_changed_policy_version_changes_fingerprint():
    assert _fingerprint(_snapshot(policy_version="1")) != _fingerprint(
        _snapshot(policy_version="2")
    )


def test_snapshot_identity_and_creation_time_are_excluded():
    first = _snapshot(
        snapshot_id="snapshot-a",
        created_at=datetime(2026, 8, 16, tzinfo=timezone.utc),
        fingerprint="existing-fingerprint-a",
    )
    second = _snapshot(
        snapshot_id="snapshot-b",
        created_at=datetime(2026, 8, 17, tzinfo=timezone.utc),
        fingerprint="existing-fingerprint-b",
    )

    assert _fingerprint(first) == _fingerprint(second)


def test_result_is_a_sha256_hex_digest():
    fingerprint = _fingerprint(_snapshot())

    assert len(fingerprint) == 64
    assert all(character in "0123456789abcdef" for character in fingerprint)


def test_fingerprint_domain_contains_no_vertical_or_asset_terminology():
    domain_file = (
        Path(__file__).parents[1]
        / "app"
        / "domain"
        / "workforce_auto_planning"
        / "weekly_snapshot_fingerprint.py"
    )
    source = domain_file.read_text(encoding="utf-8").lower()

    forbidden_terms = ("amazon", "dsp", "next_day", "same_day", "fleet", "vehicle")
    assert all(term not in source for term in forbidden_terms)
