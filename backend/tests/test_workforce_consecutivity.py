import json
from datetime import date, timedelta
from time import perf_counter
from types import SimpleNamespace

import pytest

from app.auth.domain import Role
from app.auth.permission_service import has_permission
from app.core.database import db_session
from app.plugins.workforce.application import consecutivity_service
from app.plugins.workforce.application.consecutivity_policy import update_policy
from app.plugins.workforce.application.consecutivity_service import (
    snapshots,
    snapshots_for_period,
)
from app.plugins.workforce.application.override_service import create_override
from app.plugins.workforce.application.planning_adapter import planning_conflicts
from app.plugins.workforce.infrastructure import consecutivity_repository, read_repository


ORG = "qa-workforce"
TARGET = date(2026, 8, 20)
NOW = "2026-08-20T08:00:00+00:00"


def member(identifier: str, organization_id: str = ORG) -> int:
    with db_session() as conn:
        cursor = conn.execute(
            """INSERT INTO workforce_members (
                external_identifier, display_name, first_name, last_name,
                role, station, employment_type, capabilities,
                operational_notes, is_reserve, active, source_reference,
                created_at, updated_at, organization_id
            ) VALUES (?, ?, ?, ?, 'driver', 'DLO1', 'Full time', '[]',
                NULL, 0, 1, 'qa', ?, ?, ?)""",
            (identifier, identifier, identifier, "Driver", NOW, NOW, organization_id),
        )
        return int(cursor.lastrowid)


def day_status(
    member_id: int,
    day: date,
    code: str,
    *,
    notes: str | None = None,
    start_time: str | None = None,
    end_time: str | None = None,
    organization_id: str = ORG,
):
    with db_session() as conn:
        conn.execute(
            """INSERT INTO workforce_day_statuses (
                workforce_member_id, date, status_code, availability,
                shift_code, start_time, end_time, notes, source_reference,
                observed_or_confirmed, updated_at, organization_id
            ) VALUES (?, ?, ?, ?, NULL, ?, ?, ?, 'qa', 'imported', ?, ?)""",
            (
                member_id, day.isoformat(), code,
                int(code in {"available", "available_limited", "scheduled"}),
                start_time, end_time, notes, NOW, organization_id,
            ),
        )


def history(member_id: int, consecutive: int):
    boundary = TARGET - timedelta(days=consecutive + 1)
    day_status(member_id, boundary, "rest")
    for offset in range(consecutive, 0, -1):
        day_status(member_id, TARGET - timedelta(days=offset), "scheduled")


def planning(
    driver_identifier: str,
    day: date,
    status: str,
    organization_id: str = ORG,
) -> int:
    with db_session() as conn:
        planning_import = conn.execute(
            """INSERT INTO imports (
                dataset_type, original_filename, imported_at, sheet_name,
                column_mapping, normalized_rows
            ) VALUES ('planning', 'qa.xlsx', ?, 'qa', '{}', '[]')""",
            (NOW,),
        ).lastrowid
        fleet_import = conn.execute(
            """INSERT INTO imports (
                dataset_type, original_filename, imported_at, sheet_name,
                column_mapping, normalized_rows
            ) VALUES ('fleet', 'qa.xlsx', ?, 'qa', '{}', '[]')""",
            (NOW,),
        ).lastrowid
        plan_id = conn.execute(
            """INSERT INTO plannings (
                operation_date, station, source_planning_import_id,
                source_fleet_import_id, status, version, reserve_threshold,
                configuration, summary, conflicts, generation_metadata,
                created_at, updated_at, organization_id
            ) VALUES (?, 'DLO1', ?, ?, ?, 1, 1, '{}', '{}', '[]', '{}', ?, ?, ?)""",
            (
                day.isoformat(), planning_import, fleet_import, status,
                NOW, NOW, organization_id,
            ),
        ).lastrowid
        conn.execute(
            """INSERT INTO assignments (
                planning_id, operation_date, station, route_id, driver_id,
                driver_name, assignment_status, assignment_source, confidence,
                reasons, data_used, warnings, alternatives, manual_override,
                confirmed, created_at, updated_at
            ) VALUES (?, ?, 'DLO1', ?, ?, ?, 'assigned', 'imported', 1,
                '[]', '[]', '[]', '[]', 0, 1, ?, ?)""",
            (plan_id, day.isoformat(), f"R-{plan_id}", driver_identifier, driver_identifier, NOW, NOW),
        )
    return int(plan_id)


def completed_journal(driver_identifier: str, day: date):
    with db_session() as conn:
        asset_id = conn.execute(
            """INSERT INTO fleet_assets (
                external_identifier, plate, category, status, availability,
                capabilities, created_at, updated_at
            ) VALUES (?, ?, 'van', 'active', 'disponibile', '[]', ?, ?)""",
            (f"ASSET-{driver_identifier}-{day}", f"QA{day.day:02d}{driver_identifier[-2:]}", NOW, NOW),
        ).lastrowid
        session_id = f"SESSION-{driver_identifier}-{day}"
        conn.execute(
            """INSERT INTO journal_sessions (
                id, token_hash, operation_type, asset_id, plate_snapshot,
                declared_driver_identifier, status, created_at, expires_at,
                completed_at, organization_id, operational_date
            ) VALUES (?, 'hash', 'check_in', ?, 'QA', ?, 'completed', ?, ?, ?, ?, ?)""",
            (session_id, asset_id, driver_identifier, NOW, NOW, NOW, ORG, day.isoformat()),
        )
        conn.execute(
            """INSERT INTO asset_movements (
                id, session_id, schema_version, organization_id,
                operational_unit_id, asset_id, plate_snapshot,
                declared_driver_identifier, operation_type, occurred_at,
                timezone, odometer_km, fuel_percentage, anomaly_present,
                client_submission_id, created_at
            ) VALUES (?, ?, '1.0', ?, 'DLO1', ?, 'QA', ?, 'check_in', ?,
                'Europe/Rome', 1000, 50, 0, ?, ?)""",
            (
                f"MOV-{driver_identifier}-{day}", session_id, ORG, asset_id,
                driver_identifier, f"{day.isoformat()}T18:00:00+02:00",
                f"CLIENT-{driver_identifier}-{day}", NOW,
            ),
        )


def calculated(*member_ids: int, target: date = TARGET):
    members = [
        item for item in read_repository.list_members(ORG)
        if item.workforce_member_id in member_ids
    ]
    return snapshots(ORG, target.isoformat(), members, today=TARGET)


def test_effective_sequences_cover_zero_two_four_five_six_and_seven_days():
    expected = {0: "regolare", 2: "regolare", 4: "regolare", 5: "attenzione", 6: "limite_raggiunto", 7: "riposo_raccomandato"}
    member_ids = {}
    for count in expected:
        member_ids[count] = member(f"DRV-{count}")
        history(member_ids[count], count)
    result = calculated(*member_ids.values())
    for count, status in expected.items():
        item = result[member_ids[count]]
        assert item.effective_consecutive_days == count
        assert item.planned_consecutive_days == count
        assert item.calculated_status == status
        assert item.reason


def test_rest_holiday_sickness_and_full_leave_break_the_sequence():
    for code in ("rest", "holiday", "sickness", "leave"):
        member_id = member(f"DRV-{code}")
        day_status(member_id, TARGET - timedelta(days=1), code)
        item = calculated(member_id)[member_id]
        assert item.effective_consecutive_days == 0
        assert item.calculated_status == "regolare"


def test_partial_leave_does_not_break_work_when_journal_confirms_the_day():
    member_id = member("DRV-PARTIAL")
    day_status(member_id, TARGET - timedelta(days=2), "rest")
    partial_day = TARGET - timedelta(days=1)
    day_status(member_id, partial_day, "leave", notes="Permesso parziale", start_time="14:00", end_time="18:00")
    completed_journal("DRV-PARTIAL", partial_day)
    item = calculated(member_id)[member_id]
    assert item.effective_consecutive_days == 1
    assert item.sequence[6].source == "journal_completed"


def test_only_confirmed_and_published_plans_extend_the_planned_sequence():
    member_id = member("DRV-PLAN")
    history(member_id, 4)
    planning("DRV-PLAN", TARGET, "published")
    planning("DRV-PLAN", TARGET + timedelta(days=1), "draft")
    item = calculated(member_id)[member_id]
    assert item.effective_consecutive_days == 4
    assert item.planned_consecutive_days == 5
    assert item.next_planned_work_date == TARGET.isoformat()
    assert item.calculated_status == "attenzione"


def test_journal_and_planning_for_the_same_day_are_deduplicated():
    member_id = member("DRV-DEDUP")
    rest_day = TARGET - timedelta(days=3)
    worked_day = TARGET - timedelta(days=2)
    day_status(member_id, rest_day, "rest")
    planning("DRV-DEDUP", worked_day, "published")
    completed_journal("DRV-DEDUP", worked_day)
    item = calculated(member_id)[member_id]
    assert item.effective_consecutive_days == 1
    matching = [day for day in item.sequence if day.date == worked_day.isoformat()]
    assert len(matching) == 1 and matching[0].source == "journal_completed"


def test_missing_history_is_not_presented_as_zero():
    member_id = member("DRV-MISSING")
    day_status(member_id, TARGET - timedelta(days=1), "scheduled")
    item = calculated(member_id)[member_id]
    assert item.effective_consecutive_days is None
    assert item.calculated_status == "dati_insufficienti"
    assert "non sufficiente" in item.reason


def test_configurable_policy_and_override_preserve_the_calculated_count_and_audit():
    member_id = member("DRV-OVERRIDE")
    history(member_id, 4)
    policy = update_policy(
        ORG, warning_threshold=3, rest_required_threshold=4,
        rest_break_days=1, actor="admin@example.test",
    )
    assert policy.warning_threshold == 3
    override = create_override(
        ORG, member_id, TARGET.isoformat(), TARGET.isoformat(),
        "callable", "Eccezione operativa verificata.", "dispatcher@example.test",
    )
    item = calculated(member_id)[member_id]
    assert item.effective_consecutive_days == 4
    assert item.calculated_status == "limite_raggiunto"
    assert item.status == "override_manual"
    assert item.override.id == override.id
    with db_session() as conn:
        audit = conn.execute(
            "SELECT reason FROM workforce_changes WHERE entity_id = ?", (override.id,)
        ).fetchone()
    assert audit["reason"] == "override_created"


def test_policy_can_require_two_complete_rest_days_before_resetting_the_sequence():
    member_id = member("DRV-TWO-RESTS")
    day_status(member_id, TARGET - timedelta(days=2), "rest")
    day_status(member_id, TARGET - timedelta(days=1), "scheduled")
    update_policy(
        ORG, warning_threshold=5, rest_required_threshold=6,
        rest_break_days=2, actor="admin@example.test",
    )
    item = calculated(member_id)[member_id]
    assert item.effective_consecutive_days is None
    assert item.calculated_status == "dati_insufficienti"

    day_status(member_id, TARGET - timedelta(days=3), "rest")
    item = calculated(member_id)[member_id]
    assert item.effective_consecutive_days == 1
    assert item.calculated_status == "regolare"


def test_expired_override_and_organization_scope_are_not_applied():
    first = member("DRV-ORG-A", ORG)
    second_org = "qa-workforce-b"
    second = member("DRV-ORG-B", second_org)
    history(first, 2)
    create_override(
        ORG, first, "2026-08-18", "2026-08-19", "callable",
        "Override scaduto.", "admin@example.test",
    )
    first_item = calculated(first)[first]
    assert first_item.override is None
    assert first_item.expired_override is not None
    other_members = read_repository.list_members(second_org)
    assert {item.workforce_member_id for item in other_members} == {second}


def test_permissions_follow_the_workforce_responsibility_matrix():
    assert has_permission(Role.ADMINISTRATOR, "workforce:policy:write")
    assert has_permission(Role.OPERATIONS_MANAGER, "workforce:override")
    assert has_permission(Role.DISPATCHER, "workforce:override")
    assert not has_permission(Role.FLEET_MANAGER, "workforce:override")
    assert has_permission(Role.VIEWER, "workforce:read")
    assert not has_permission(Role.VIEWER, "workforce:write")


def test_planning_conflict_uses_the_authoritative_workforce_snapshot():
    consecutivity = SimpleNamespace(
        calculated_status="riposo_raccomandato",
        reason="Settimo giorno consecutivo pianificato.",
        override=None,
        expired_override=None,
        effective_consecutive_days=6,
        planned_consecutive_days=7,
        threshold_warning=5,
        threshold_rest_required=6,
    )
    driver = SimpleNamespace(
        external_identifier="DRV-BLOCKED",
        display_name="Driver Bloccato",
        consecutivity=consecutivity,
    )
    snapshot = SimpleNamespace(
        operation_date=TARGET.isoformat(), drivers=[driver],
    )
    conflicts = planning_conflicts(
        snapshot, [{"driver_id": "DRV-BLOCKED"}],
    )
    assert len(conflicts) == 1
    assert conflicts[0]["blocking"] is True
    assert conflicts[0]["count_after_assignment"] == 7
    assert conflicts[0]["workforce_target"] == "workforce"
    assert "7 giorni" in conflicts[0]["message"]


def test_planning_reports_an_expired_override_when_the_driver_remains_blocked():
    expired = SimpleNamespace(id="expired-override")
    consecutivity = SimpleNamespace(
        calculated_status="limite_raggiunto",
        reason="Limite raggiunto.",
        override=None,
        expired_override=expired,
        effective_consecutive_days=6,
        planned_consecutive_days=6,
        threshold_warning=5,
        threshold_rest_required=6,
    )
    driver = SimpleNamespace(
        external_identifier="DRV-EXPIRED",
        display_name="Driver Override Scaduto",
        consecutivity=consecutivity,
    )
    snapshot = SimpleNamespace(
        operation_date=TARGET.isoformat(), drivers=[driver],
    )
    conflict = planning_conflicts(
        snapshot, [{"driver_id": "DRV-EXPIRED"}],
    )[0]
    assert conflict["message"] == "Override Workforce scaduto."
    assert conflict["blocking"] is True


def test_thirty_driver_fourteen_day_qa_matrix_covers_operational_states():
    expected_counts = [0, 2, 4, 5, 6, 7, None] * 4 + [5, 6]
    member_ids = []
    for index, count in enumerate(expected_counts):
        member_id = member(f"MATRIX-{index + 1:02d}")
        member_ids.append(member_id)
        if count is None:
            day_status(member_id, TARGET - timedelta(days=1), "scheduled")
            continue
        boundary_offset = count + 1
        for offset in range(14, boundary_offset - 1, -1):
            day_status(member_id, TARGET - timedelta(days=offset), "rest")
        for offset in range(count, 0, -1):
            day_status(member_id, TARGET - timedelta(days=offset), "scheduled")

    result = calculated(*member_ids)
    assert len(result) == 30
    statuses = {item.calculated_status for item in result.values()}
    assert statuses == {
        "regolare", "attenzione", "limite_raggiunto",
        "riposo_raccomandato", "dati_insufficienti",
    }
    assert all(len(item.sequence) == 14 for item in result.values())


def test_150_drivers_and_60_days_are_calculated_in_one_aggregated_pass():
    ids = [member(f"PERF-{index:03d}") for index in range(150)]
    rows = []
    for member_id in ids:
        for offset in range(60, 0, -1):
            day = TARGET - timedelta(days=offset)
            code = "rest" if offset == 60 else "scheduled"
            rows.append((member_id, day.isoformat(), code, int(code == "scheduled"), NOW, ORG))
    with db_session() as conn:
        conn.executemany(
            """INSERT INTO workforce_day_statuses (
                workforce_member_id, date, status_code, availability,
                source_reference, observed_or_confirmed, updated_at,
                organization_id
            ) VALUES (?, ?, ?, ?, 'perf', 'imported', ?, ?)""",
            rows,
        )
    started = perf_counter()
    result = calculated(*ids)
    elapsed = perf_counter() - started
    assert len(result) == 150
    assert elapsed < 2.0


def _snapshot_without_runtime_timestamp(item):
    payload = item.model_dump(mode="json")
    payload.pop("calculated_at")
    return payload


def test_period_batch_matches_authoritative_daily_snapshots_for_each_date():
    member_id = member("BATCH-EQUIVALENCE")
    day_status(member_id, TARGET - timedelta(days=4), "rest")
    for offset in (3, 2, 1):
        day_status(member_id, TARGET - timedelta(days=offset), "scheduled")
    planning("BATCH-EQUIVALENCE", TARGET, "published")
    members = [
        item for item in read_repository.list_members(ORG)
        if item.workforce_member_id == member_id
    ]
    period_end = TARGET + timedelta(days=2)

    batch = snapshots_for_period(
        ORG, TARGET.isoformat(), period_end.isoformat(), members, today=TARGET
    )

    for offset in range(3):
        operation_day = TARGET + timedelta(days=offset)
        daily = snapshots(
            ORG, operation_day.isoformat(), members, today=TARGET
        )[member_id]
        assert _snapshot_without_runtime_timestamp(
            batch[operation_day.isoformat()][member_id]
        ) == _snapshot_without_runtime_timestamp(daily)


def test_period_batch_preserves_source_precedence_policy_and_override_lifecycle():
    member_id = member("BATCH-PRECEDENCE")
    day_status(member_id, TARGET - timedelta(days=3), "rest")
    worked_day = TARGET - timedelta(days=2)
    planning("BATCH-PRECEDENCE", worked_day, "published")
    completed_journal("BATCH-PRECEDENCE", worked_day)
    day_status(member_id, TARGET - timedelta(days=1), "scheduled")
    update_policy(
        ORG,
        warning_threshold=2,
        rest_required_threshold=3,
        rest_break_days=1,
        actor="admin@example.test",
    )
    create_override(
        ORG,
        member_id,
        (TARGET + timedelta(days=1)).isoformat(),
        (TARGET + timedelta(days=1)).isoformat(),
        "callable",
        "Override batch controllato.",
        "dispatcher@example.test",
    )
    members = [
        item for item in read_repository.list_members(ORG)
        if item.workforce_member_id == member_id
    ]

    batch = snapshots_for_period(
        ORG,
        TARGET.isoformat(),
        (TARGET + timedelta(days=2)).isoformat(),
        members,
        today=TARGET,
    )

    first = batch[TARGET.isoformat()][member_id]
    active = batch[(TARGET + timedelta(days=1)).isoformat()][member_id]
    expired = batch[(TARGET + timedelta(days=2)).isoformat()][member_id]
    daily_active = snapshots(
        ORG,
        (TARGET + timedelta(days=1)).isoformat(),
        members,
        today=TARGET,
    )[member_id]
    journal_day = next(item for item in first.sequence if item.date == worked_day.isoformat())
    assert journal_day.source == "journal_completed"
    assert first.threshold_warning == 2
    assert first.threshold_rest_required == 3
    assert first.override is None
    assert first.expired_override is None
    assert active.status == "override_manual"
    assert active.override is not None
    assert active.expired_override is None
    assert _snapshot_without_runtime_timestamp(active) == _snapshot_without_runtime_timestamp(
        daily_active
    )
    assert expired.override is None
    assert expired.expired_override is not None


def test_period_batch_is_date_and_member_ordered_and_supports_general_periods():
    first_id = member("BATCH-ORDER-1")
    second_id = member("BATCH-ORDER-2")
    day_status(second_id, TARGET - timedelta(days=2), "rest")
    day_status(second_id, TARGET - timedelta(days=1), "scheduled")
    members = [
        item for item in read_repository.list_members(ORG)
        if item.workforce_member_id in {first_id, second_id}
    ]
    forward_members = list(members)
    members.reverse()
    period_end = TARGET + timedelta(days=9)

    result = snapshots_for_period(
        ORG, TARGET.isoformat(), period_end.isoformat(), members, today=TARGET
    )

    assert list(result) == [
        (TARGET + timedelta(days=offset)).isoformat() for offset in range(10)
    ]
    assert all(list(items) == sorted((first_id, second_id)) for items in result.values())
    assert result[TARGET.isoformat()][first_id].effective_consecutive_days is None
    assert result[TARGET.isoformat()][second_id].effective_consecutive_days == 1

    forward_result = snapshots_for_period(
        ORG,
        TARGET.isoformat(),
        period_end.isoformat(),
        forward_members,
        today=TARGET,
    )
    for operation_date, items in result.items():
        for member_id, item in items.items():
            assert _snapshot_without_runtime_timestamp(item) == (
                _snapshot_without_runtime_timestamp(
                    forward_result[operation_date][member_id]
                )
            )


def test_period_batch_does_not_apply_revoked_overrides():
    member_id = member("BATCH-REVOKED")
    revoked = create_override(
        ORG,
        member_id,
        TARGET.isoformat(),
        TARGET.isoformat(),
        "callable",
        "Override poi revocato.",
        "dispatcher@example.test",
    )
    with db_session() as conn:
        conn.execute(
            "UPDATE workforce_consecutivity_overrides SET revoked_at = ? WHERE id = ?",
            (NOW, revoked.id),
        )
    members = [
        item for item in read_repository.list_members(ORG)
        if item.workforce_member_id == member_id
    ]

    item = snapshots_for_period(
        ORG, TARGET.isoformat(), TARGET.isoformat(), members, today=TARGET
    )[TARGET.isoformat()][member_id]

    assert item.override is None
    assert item.expired_override is None


def test_period_batch_rejects_invalid_scope_period_and_cross_tenant_members():
    local_id = member("BATCH-SCOPE-SHARED")
    foreign_org = "qa-workforce-foreign"
    foreign_id = member("BATCH-SCOPE-SHARED", foreign_org)
    day_status(
        foreign_id,
        TARGET - timedelta(days=1),
        "scheduled",
        organization_id=foreign_org,
    )
    local_member = next(
        item for item in read_repository.list_members(ORG)
        if item.workforce_member_id == local_id
    )
    foreign_member = next(
        item for item in read_repository.list_members(foreign_org)
        if item.workforce_member_id == foreign_id
    )
    local_result = snapshots_for_period(
        ORG,
        TARGET.isoformat(),
        TARGET.isoformat(),
        [local_member],
        today=TARGET,
    )[TARGET.isoformat()][local_id]
    assert local_result.effective_consecutive_days is None
    with pytest.raises(ValueError, match="organization_id is required"):
        snapshots_for_period("   ", TARGET.isoformat(), TARGET.isoformat(), [])
    with pytest.raises(ValueError, match="period_end"):
        snapshots_for_period(
            ORG,
            TARGET.isoformat(),
            (TARGET - timedelta(days=1)).isoformat(),
            [local_member],
        )
    with pytest.raises(ValueError, match="members must belong"):
        snapshots_for_period(
            ORG,
            TARGET.isoformat(),
            TARGET.isoformat(),
            [local_member, foreign_member],
            today=TARGET,
        )


def test_period_batch_uses_explicit_today_and_loads_each_batch_dependency_once(
    monkeypatch,
):
    member_id = member("BATCH-LOADS")
    members = [
        item for item in read_repository.list_members(ORG)
        if item.workforce_member_id == member_id
    ]
    calls = {"rows": 0, "policy": 0, "overrides": 0}
    original_rows = consecutivity_repository.source_rows_for_organization
    original_policy = consecutivity_repository.get_policy
    original_overrides = consecutivity_repository.override_candidates_for_period

    def counted_rows(*args, **kwargs):
        calls["rows"] += 1
        return original_rows(*args, **kwargs)

    def counted_policy(*args, **kwargs):
        calls["policy"] += 1
        return original_policy(*args, **kwargs)

    def counted_overrides(*args, **kwargs):
        calls["overrides"] += 1
        return original_overrides(*args, **kwargs)

    monkeypatch.setattr(
        consecutivity_repository, "source_rows_for_organization", counted_rows
    )
    monkeypatch.setattr(consecutivity_repository, "get_policy", counted_policy)
    monkeypatch.setattr(
        consecutivity_repository, "override_candidates_for_period", counted_overrides
    )
    monkeypatch.setattr(
        consecutivity_service,
        "_organization_today",
        lambda _organization_id: (_ for _ in ()).throw(
            AssertionError("today must not be resolved implicitly")
        ),
    )

    result = snapshots_for_period(
        ORG,
        TARGET.isoformat(),
        (TARGET + timedelta(days=6)).isoformat(),
        members,
        today=TARGET,
    )

    assert len(result) == 7
    assert calls == {"rows": 1, "policy": 1, "overrides": 1}
