from datetime import date, timedelta

import pytest

from app.core.database import db_session
from app.plugins.workforce.application import availability_service
from app.plugins.workforce.application.availability_service import (
    foundation_snapshot,
    readiness_for_period,
)
from app.plugins.workforce.application.consecutivity_service import snapshots_for_period
from app.plugins.workforce.domain.consecutivity import ConsecutivitySnapshot
from app.plugins.workforce.infrastructure import read_repository


ORG = "qa-weekly-availability"
TARGET = date(2026, 8, 20)
NOW = "2026-08-20T08:00:00+00:00"


def _member(
    identifier: str,
    *,
    organization_id: str = ORG,
    active: bool = True,
    reserve: bool = False,
) -> int:
    with db_session() as conn:
        cursor = conn.execute(
            """INSERT INTO workforce_members (
                external_identifier, display_name, first_name, last_name,
                role, station, employment_type, capabilities,
                operational_notes, is_reserve, active, source_reference,
                created_at, updated_at, organization_id
            ) VALUES (?, ?, ?, 'Driver', 'driver', 'DLO1', 'Full time', '[]',
                NULL, ?, ?, 'weekly-availability-test', ?, ?, ?)""",
            (
                identifier,
                identifier,
                identifier,
                int(reserve),
                int(active),
                NOW,
                NOW,
                organization_id,
            ),
        )
        return int(cursor.lastrowid)


def _status(
    member_id: int,
    day: date,
    code: str,
    *,
    organization_id: str = ORG,
    notes: str | None = None,
) -> None:
    with db_session() as conn:
        conn.execute(
            """INSERT INTO workforce_day_statuses (
                workforce_member_id, date, status_code, availability,
                notes, source_reference, observed_or_confirmed, updated_at,
                organization_id
            ) VALUES (?, ?, ?, ?, ?, 'weekly-availability-test', 'manual', ?, ?)""",
            (
                member_id,
                day.isoformat(),
                code,
                int(code in {"available", "scheduled", "available_limited"}),
                notes,
                NOW,
                organization_id,
            ),
        )


def _members(organization_id: str = ORG):
    return [
        item for item in read_repository.list_members(organization_id)
        if item.organization_id == organization_id
    ]


def _consecutivity(
    member_id: int,
    operation_date: str,
    *,
    organization_id: str = ORG,
    effective: int | None = 1,
    calculated_status: str = "regolare",
) -> ConsecutivitySnapshot:
    return ConsecutivitySnapshot(
        driver_id=member_id,
        operation_date=operation_date,
        organization_id=organization_id,
        effective_consecutive_days=effective,
        planned_consecutive_days=effective,
        threshold_warning=5,
        threshold_rest_required=6,
        status=calculated_status,
        calculated_status=calculated_status,
        reason="Valutazione test deterministica.",
        source_summary=["workforce_history"],
        calculated_at=NOW,
        analyzed_from=(date.fromisoformat(operation_date) - timedelta(days=60)).isoformat(),
        analyzed_to=(date.fromisoformat(operation_date) - timedelta(days=1)).isoformat(),
    )


def _without_runtime_timestamp(item):
    payload = item.model_dump(mode="json")
    if payload["consecutivity"]:
        payload["consecutivity"].pop("calculated_at")
    return payload


def test_single_day_batch_matches_authoritative_foundation_classification():
    member_id = _member("AVAILABILITY-PARITY")
    _status(member_id, TARGET - timedelta(days=2), "rest")
    _status(member_id, TARGET - timedelta(days=1), "scheduled")
    _status(member_id, TARGET, "available")
    members = _members()
    consecutivity = snapshots_for_period(
        ORG, TARGET.isoformat(), TARGET.isoformat(), members, today=TARGET
    )

    batch_item = readiness_for_period(
        organization_id=ORG,
        period_start=TARGET.isoformat(),
        period_end=TARGET.isoformat(),
        members=members,
        consecutivity_by_date=consecutivity,
    )[TARGET.isoformat()][0]
    legacy_item = next(
        item for item in foundation_snapshot(TARGET.isoformat(), ORG).drivers
        if item.workforce_member_id == member_id
    )

    assert _without_runtime_timestamp(batch_item) == _without_runtime_timestamp(
        legacy_item
    )


def test_batch_preserves_all_status_decisions_and_limited_reason():
    cases = {
        "available": ("available", "callable", True),
        "scheduled": ("scheduled", "callable", True),
        "available_limited": ("available_limited", "limited", True),
        "rest": ("rest", "not_callable", False),
        "holiday": ("holiday", "not_callable", False),
        "sickness": ("sickness", "not_callable", False),
        "leave": ("leave", "not_callable", False),
        "unavailable": ("unavailable", "not_callable", False),
        "unexpected-source-code": ("unknown", "not_callable", False),
    }
    snapshots = {}
    for index, (source_status, _expected) in enumerate(cases.items(), start=1):
        member_id = _member(f"AVAILABILITY-{index:02d}")
        notes = "Limitazione verificata." if source_status == "available_limited" else None
        _status(member_id, TARGET, source_status, notes=notes)
        snapshots[member_id] = _consecutivity(member_id, TARGET.isoformat())

    items = readiness_for_period(
        organization_id=ORG,
        period_start=TARGET.isoformat(),
        period_end=TARGET.isoformat(),
        members=_members(),
        consecutivity_by_date={TARGET.isoformat(): snapshots},
    )[TARGET.isoformat()]
    by_identifier = {item.external_identifier: item for item in items}

    for index, (_source, expected) in enumerate(cases.items(), start=1):
        item = by_identifier[f"AVAILABILITY-{index:02d}"]
        availability_status, callability_status, callable_value = expected
        assert item.availability_status == availability_status
        assert item.callability_status == callability_status
        assert item.callable is callable_value
    limited = by_identifier["AVAILABILITY-03"]
    assert limited.callability_reason == "Limitazione verificata."
    assert limited.limitations == ["Limitazione verificata."]


def test_missing_consecutivity_stays_unknown_and_inactive_members_stay_excluded():
    active_id = _member("AVAILABILITY-NO-CONSECUTIVITY")
    inactive_id = _member("AVAILABILITY-INACTIVE", active=False)
    _status(active_id, TARGET, "available")
    _status(inactive_id, TARGET, "available")

    items = readiness_for_period(
        organization_id=ORG,
        period_start=TARGET.isoformat(),
        period_end=TARGET.isoformat(),
        members=_members(),
        consecutivity_by_date={},
    )[TARGET.isoformat()]

    assert [item.workforce_member_id for item in items] == [active_id]
    assert items[0].consecutive_days is None
    assert items[0].consecutivity_status == "not_evaluated"
    assert items[0].consecutivity is None


def test_batch_is_strictly_organization_scoped_without_default_fallback():
    local_id = _member("AVAILABILITY-SHARED")
    foreign_org = "qa-weekly-availability-foreign"
    foreign_id = _member("AVAILABILITY-SHARED", organization_id=foreign_org)
    default_id = _member("AVAILABILITY-DEFAULT", organization_id="default")
    _status(foreign_id, TARGET, "scheduled", organization_id=foreign_org)
    _status(default_id, TARGET, "scheduled", organization_id="default")
    local_member = _members()[0]
    foreign_member = _members(foreign_org)[0]

    local_items = readiness_for_period(
        organization_id=ORG,
        period_start=TARGET.isoformat(),
        period_end=TARGET.isoformat(),
        members=[local_member],
        consecutivity_by_date={},
    )[TARGET.isoformat()]

    assert len(local_items) == 1
    assert local_items[0].workforce_member_id == local_id
    assert local_items[0].availability_status == "unknown"
    assert local_items[0].callable is False
    with pytest.raises(ValueError, match="members must belong"):
        readiness_for_period(
            organization_id=ORG,
            period_start=TARGET.isoformat(),
            period_end=TARGET.isoformat(),
            members=[local_member, foreign_member],
            consecutivity_by_date={},
        )


def test_batch_validates_period_and_is_independent_from_member_input_order():
    first_id = _member("AVAILABILITY-ORDER-A")
    second_id = _member("AVAILABILITY-ORDER-B")
    _status(first_id, TARGET, "available")
    _status(second_id, TARGET, "available_limited", notes="Limitazione B.")
    members = _members()
    indexed = {
        first_id: _consecutivity(first_id, TARGET.isoformat()),
        second_id: _consecutivity(second_id, TARGET.isoformat()),
    }

    forward = readiness_for_period(
        organization_id=ORG,
        period_start=TARGET.isoformat(),
        period_end=TARGET.isoformat(),
        members=members,
        consecutivity_by_date={TARGET.isoformat(): indexed},
    )
    reverse = readiness_for_period(
        organization_id=ORG,
        period_start=TARGET.isoformat(),
        period_end=TARGET.isoformat(),
        members=list(reversed(members)),
        consecutivity_by_date={TARGET.isoformat(): indexed},
    )

    assert forward == reverse
    with pytest.raises(ValueError, match="organization_id is required"):
        readiness_for_period(
            organization_id=" ",
            period_start=TARGET.isoformat(),
            period_end=TARGET.isoformat(),
            members=[],
            consecutivity_by_date={},
        )
    with pytest.raises(ValueError, match="period_end"):
        readiness_for_period(
            organization_id=ORG,
            period_start=TARGET.isoformat(),
            period_end=(TARGET - timedelta(days=1)).isoformat(),
            members=members,
            consecutivity_by_date={},
        )


def test_seven_day_batch_loads_statuses_once_and_never_recalculates_consecutivity(
    monkeypatch,
):
    member_id = _member("AVAILABILITY-CALL-COUNT")
    _status(member_id, TARGET, "available")
    members = _members()
    period_end = TARGET + timedelta(days=6)
    indexed = {
        (TARGET + timedelta(days=offset)).isoformat(): {
            member_id: _consecutivity(
                member_id, (TARGET + timedelta(days=offset)).isoformat()
            )
        }
        for offset in range(7)
    }
    calls = {"statuses": 0}
    original_statuses = read_repository.list_statuses_strict

    def counted_statuses(*args, **kwargs):
        calls["statuses"] += 1
        return original_statuses(*args, **kwargs)

    monkeypatch.setattr(read_repository, "list_statuses_strict", counted_statuses)
    monkeypatch.setattr(
        read_repository,
        "list_members",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("members must come from the caller")
        ),
    )
    monkeypatch.setattr(
        availability_service,
        "consecutivity_snapshots",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("consecutivity must come from E3")
        ),
    )

    result = readiness_for_period(
        organization_id=ORG,
        period_start=TARGET.isoformat(),
        period_end=period_end.isoformat(),
        members=members,
        consecutivity_by_date=indexed,
    )

    assert len(result) == 7
    assert calls == {"statuses": 1}
    first = result[TARGET.isoformat()][0]
    assert first.consecutive_days == 1
    assert first.consecutivity == indexed[TARGET.isoformat()][member_id]
