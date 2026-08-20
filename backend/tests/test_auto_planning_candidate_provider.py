from contextlib import contextmanager
from datetime import date
from pathlib import Path

import pytest

from app.core.database import db_session
from app.domain.core_language import OperationalUnit
from app.domain.workforce_auto_planning import (
    CandidateOperationalUnitScopeStatus,
    WorkforceCandidateSnapshotProvider,
)
from app.plugins.workforce.application.auto_planning_candidate_provider import (
    WorkforceCandidateSnapshotProviderAdapter,
)
from app.plugins.workforce.application.workforce_candidate_mapper import (
    map_workforce_candidate,
)
from app.plugins.workforce.domain.consecutivity import ConsecutivitySnapshot
from app.plugins.workforce.domain.driver_shift_planning import (
    DriverShiftPlanningPublishedRow,
)
from app.plugins.workforce.domain.models import (
    WorkforceDriverReadiness,
    WorkforceMember,
)
from app.plugins.workforce.infrastructure import read_repository


ORG = "qa-auto-planning-candidate-provider"
OTHER_ORG = "qa-auto-planning-candidate-provider-other"
START = date(2026, 8, 17)
END = date(2026, 8, 23)
UNIT = OperationalUnit(external_identifier="unit-north")


def _member(
    member_id: int,
    identifier: str,
    *,
    station: str | None,
    active: bool = True,
    organization_id: str = ORG,
) -> WorkforceMember:
    return WorkforceMember(
        workforce_member_id=member_id,
        external_identifier=identifier,
        display_name=f"Driver {identifier}",
        station=station,
        employment_type="full-time",
        weekly_hours=40,
        capabilities=["parcel-delivery"],
        is_reserve=False,
        active=active,
        source_reference="candidate-provider-test",
        created_at="2026-08-01T08:00:00+00:00",
        updated_at="2026-08-16T08:00:00+00:00",
        organization_id=organization_id,
    )


def _consecutivity(member_id: int, operation_date: str, value: int):
    return ConsecutivitySnapshot(
        driver_id=member_id,
        operation_date=operation_date,
        organization_id=ORG,
        effective_consecutive_days=value,
        planned_consecutive_days=value + 1,
        threshold_warning=5,
        threshold_rest_required=6,
        status="eligible",
        calculated_status="regolare",
        reason="Consecutivita regolare.",
        calculated_at="2026-08-16T08:00:00+00:00",
        analyzed_from="2026-08-10",
        analyzed_to="2026-08-16",
    )


def _readiness(member: WorkforceMember) -> WorkforceDriverReadiness:
    return WorkforceDriverReadiness(
        workforce_member_id=member.workforce_member_id,
        external_identifier=member.external_identifier,
        first_name="Driver",
        last_name=member.external_identifier,
        display_name=member.display_name,
        station=member.station,
        contract=member.employment_type,
        availability_status="available",
        availability_label="Disponibile",
        callability_status="callable",
        callability_label="Convocabile",
        callability_reason="Nessuna limitazione.",
        callability_tone="success",
        callable=True,
        capabilities=member.capabilities,
        last_updated_at="2026-08-16T08:00:00+00:00",
    )


def _assignment(row_id: int, member_id: int) -> DriverShiftPlanningPublishedRow:
    return DriverShiftPlanningPublishedRow(
        id=row_id,
        organization_id=ORG,
        driver_shift_planning_id=9,
        planning_version=1,
        workforce_member_id=member_id,
        operational_date=START.isoformat(),
        status_code="scheduled",
        availability=True,
        shift_code="morning",
        start_time="08:00",
        end_time="12:00",
        station="unit-north",
        provenance_summary=[],
        published_at="2026-08-16T09:00:00+00:00",
    )


def test_provider_implements_port_and_orchestrates_each_batch_once():
    matched = _member(1, "driver-b", station="unit-north")
    mismatched = _member(2, "driver-a", station="unit-south")
    unknown = _member(3, "driver-c", station=None)
    inactive = _member(4, "driver-inactive", station="unit-north", active=False)
    calls = {
        "members": 0,
        "e3": 0,
        "e4": 0,
        "e5": 0,
        "mapper": 0,
    }
    captured = {"batch_members": (), "mapped": []}

    def member_loader(organization_id):
        calls["members"] += 1
        assert organization_id == ORG
        return [unknown, inactive, matched, mismatched]

    def consecutivity_batch(organization_id, period_start, period_end, members):
        calls["e3"] += 1
        assert (organization_id, period_start, period_end) == (
            ORG,
            START.isoformat(),
            END.isoformat(),
        )
        captured["batch_members"] = tuple(members)
        return {
            START.isoformat(): {
                member.workforce_member_id: _consecutivity(
                    member.workforce_member_id,
                    START.isoformat(),
                    member.workforce_member_id,
                )
                for member in members
            },
            END.isoformat(): {
                member.workforce_member_id: _consecutivity(
                    member.workforce_member_id,
                    END.isoformat(),
                    20 + member.workforce_member_id,
                )
                for member in members
            },
        }

    def availability_batch(**kwargs):
        calls["e4"] += 1
        assert kwargs["organization_id"] == ORG
        assert kwargs["period_start"] == START.isoformat()
        assert kwargs["period_end"] == END.isoformat()
        assert tuple(kwargs["members"]) == captured["batch_members"]
        return {
            START.isoformat(): tuple(
                _readiness(member) for member in kwargs["members"]
            )
        }

    def published_shift_batch(organization_id, period_start, period_end):
        calls["e5"] += 1
        assert (organization_id, period_start, period_end) == (
            ORG,
            START.isoformat(),
            END.isoformat(),
        )
        return [_assignment(3, matched.workforce_member_id),
                _assignment(1, unknown.workforce_member_id),
                _assignment(2, matched.workforce_member_id)]

    def candidate_mapper(**kwargs):
        calls["mapper"] += 1
        captured["mapped"].append(kwargs)
        return map_workforce_candidate(**kwargs)

    provider = WorkforceCandidateSnapshotProviderAdapter(
        member_loader=member_loader,
        consecutivity_batch=consecutivity_batch,
        availability_batch=availability_batch,
        published_shift_batch=published_shift_batch,
        candidate_mapper=candidate_mapper,
    )

    assert isinstance(provider, WorkforceCandidateSnapshotProvider)
    result = provider.get_candidates(
        organization_id=ORG,
        period_start=START,
        period_end=END,
        operational_unit=UNIT,
    )

    assert isinstance(result, tuple)
    assert calls == {"members": 1, "e3": 1, "e4": 1, "e5": 1, "mapper": 3}
    assert [item.workforce_member_id for item in result] == [
        "driver-a",
        "driver-b",
        "driver-c",
    ]
    assert inactive not in captured["batch_members"]
    by_identifier = {item.workforce_member_id: item for item in result}
    assert by_identifier["driver-b"].operational_unit_scope.status == (
        CandidateOperationalUnitScopeStatus.MATCHED
    )
    assert by_identifier["driver-a"].operational_unit_scope.status == (
        CandidateOperationalUnitScopeStatus.MISMATCHED
    )
    assert by_identifier["driver-c"].operational_unit_scope.status == (
        CandidateOperationalUnitScopeStatus.UNKNOWN
    )
    assert by_identifier["driver-a"].recent_consecutivity == 2
    assert by_identifier["driver-b"].recent_consecutivity == 1
    assert by_identifier["driver-c"].recent_consecutivity == 3
    assert len(by_identifier["driver-b"].already_approved_assignments) == 2
    assert len(by_identifier["driver-c"].already_approved_assignments) == 1
    assert by_identifier["driver-a"].already_approved_assignments == ()
    assert all(
        set(item["readiness_by_date"]) == {START.isoformat()}
        for item in captured["mapped"]
    )


def _insert_member(identifier: str, organization_id: str, active: bool) -> int:
    with db_session() as conn:
        cursor = conn.execute(
            """
            INSERT INTO workforce_members (
                external_identifier, display_name, capabilities, active,
                source_reference, created_at, updated_at, organization_id
            ) VALUES (?, ?, '[]', ?, 'candidate-provider-strict-test',
                      '2026-08-16T08:00:00Z', '2026-08-16T08:00:00Z', ?)
            """,
            (identifier, f"Driver {identifier}", int(active), organization_id),
        )
        return int(cursor.lastrowid)


def test_strict_active_member_loader_is_one_query_without_default_fallback(monkeypatch):
    local_b = _insert_member("strict-b", ORG, True)
    local_a = _insert_member("strict-a", ORG, True)
    _insert_member("strict-inactive", ORG, False)
    _insert_member("strict-foreign", OTHER_ORG, True)
    _insert_member("strict-default", "default", True)
    real_db_session = db_session
    calls = {"queries": 0}

    class CountedConnection:
        def __init__(self, connection):
            self._connection = connection

        def execute(self, statement, parameters=()):
            calls["queries"] += 1
            return self._connection.execute(statement, parameters)

        def __getattr__(self, name):
            return getattr(self._connection, name)

    @contextmanager
    def counted_db_session():
        with real_db_session() as connection:
            yield CountedConnection(connection)

    monkeypatch.setattr(read_repository, "db_session", counted_db_session)

    result = read_repository.list_active_members_strict(ORG)

    assert calls == {"queries": 1}
    assert [item.workforce_member_id for item in result] == [local_a, local_b]
    assert all(item.organization_id == ORG and item.active for item in result)


def _successful_dependencies():
    member = _member(1, "driver-a", station="unit-north")

    def member_loader(_organization_id):
        return [member]

    def consecutivity_batch(_organization_id, period_start, _period_end, _members):
        return {
            period_start: {1: _consecutivity(1, period_start, 1)}
        }

    def availability_batch(**kwargs):
        return {kwargs["period_start"]: (_readiness(member),)}

    def published_shift_batch(_organization_id, _period_start, _period_end):
        return []

    return {
        "member_loader": member_loader,
        "consecutivity_batch": consecutivity_batch,
        "availability_batch": availability_batch,
        "published_shift_batch": published_shift_batch,
        "candidate_mapper": map_workforce_candidate,
    }


@pytest.mark.parametrize(
    "dependency",
    [
        "member_loader",
        "consecutivity_batch",
        "availability_batch",
        "published_shift_batch",
        "candidate_mapper",
    ],
)
def test_dependency_errors_are_propagated_without_partial_fallback(dependency):
    dependencies = _successful_dependencies()

    def fail(*_args, **_kwargs):
        raise RuntimeError(f"{dependency} failed")

    dependencies[dependency] = fail
    provider = WorkforceCandidateSnapshotProviderAdapter(**dependencies)

    with pytest.raises(RuntimeError, match=f"{dependency} failed"):
        provider.get_candidates(
            organization_id=ORG,
            period_start=START,
            period_end=END,
            operational_unit=UNIT,
        )


def test_provider_rejects_cross_organization_member_loader_output():
    dependencies = _successful_dependencies()
    dependencies["member_loader"] = lambda _organization_id: [
        _member(1, "foreign", station="unit-north", organization_id=OTHER_ORG)
    ]
    provider = WorkforceCandidateSnapshotProviderAdapter(**dependencies)

    with pytest.raises(ValueError, match="different organization"):
        provider.get_candidates(
            organization_id=ORG,
            period_start=START,
            period_end=END,
            operational_unit=UNIT,
        )


def test_provider_source_contains_no_vertical_or_direct_query_logic():
    source = (
        Path(__file__).parents[1]
        / "app"
        / "plugins"
        / "workforce"
        / "application"
        / "auto_planning_candidate_provider.py"
    ).read_text(encoding="utf-8").lower()

    forbidden_terms = (
        "amazon",
        "dsp",
        "next_day",
        "same_day",
        "db_session",
        "select ",
        "current_organization_id",
    )
    assert all(term not in source for term in forbidden_terms)
