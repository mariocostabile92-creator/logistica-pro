from datetime import date, timedelta
from itertools import count
from time import perf_counter

import pytest
from fastapi.testclient import TestClient

from app.core.database import db_session
from app.main import app
from app.plugins.workforce.application import driver_shift_credentials_service
from app.plugins.workforce.application import driver_shift_distribution_service
from app.plugins.workforce.application import driver_shift_driver_session_service
from app.plugins.workforce.application import driver_shift_planning_service
from app.plugins.workforce.application import driver_shift_portal_service
from app.plugins.workforce.application import legacy_canonical_publication_bridge as bridge
from app.plugins.workforce.domain.driver_shift_planning import (
    DriverShiftPlanningConflictError,
    DriverShiftPlanningPublishBlockedError,
)
from app.plugins.workforce.infrastructure import (
    legacy_canonical_publication_repository as bridge_repository,
)


ORG = "test-organization"
BASE = "/api/plugins/workforce/v1"
_IMPORT_SEQUENCE = count(1)


def _member(external_identifier: str, organization_id: str = ORG) -> int:
    with db_session() as conn:
        cursor = conn.execute(
            """
            INSERT INTO workforce_members (
                external_identifier, display_name, capabilities, active,
                source_reference, created_at, updated_at, organization_id
            ) VALUES (?, ?, '[]', 1, 'legacy-bridge-test',
                      '2026-08-11T09:00:00Z', '2026-08-11T09:00:00Z', ?)
            """,
            (external_identifier, f"Driver {external_identifier}", organization_id),
        )
        return int(cursor.lastrowid)


def _legacy_import(organization_id: str = ORG) -> int:
    with db_session() as conn:
        cursor = conn.execute(
            """
            INSERT INTO workforce_imports (
                fingerprint, original_filename, imported_at, sheets,
                summary, organization_id
            ) VALUES (?, 'Planning legacy.xlsx', '2026-08-08T10:23:10Z', '[]', '{}', ?)
            """,
            (f"legacy-{organization_id}-{next(_IMPORT_SEQUENCE)}", organization_id),
        )
        return int(cursor.lastrowid)


def _legacy_planning(
    organization_id: str = ORG,
    start: str = "2026-08-10",
    end: str = "2026-08-16",
):
    planning = driver_shift_planning_service.create_driver_shift_planning(
        organization_id, start, end, "Planning legacy", actor="qa@test"
    )
    driver_shift_planning_service.add_source(
        organization_id, planning.id, _legacy_import(organization_id), actor="qa@test"
    )
    return driver_shift_planning_service.get_driver_shift_planning(
        organization_id, planning.id
    )


def _status(
    member_id: int,
    operation_date: str,
    *,
    status: str = "scheduled",
    available: int = 1,
    shift: str | None = "C1",
    organization_id: str = ORG,
    source_reference: str = "Planning:row:2",
) -> None:
    with db_session() as conn:
        conn.execute(
            """
            INSERT INTO workforce_day_statuses (
                workforce_member_id, date, status_code, availability, shift_code,
                start_time, end_time, notes, source_reference,
                observed_or_confirmed, updated_at, organization_id
            ) VALUES (?, ?, ?, ?, ?, NULL, NULL, 'Nota reale', ?, 'imported',
                      '2026-08-08T10:23:10Z', ?)
            """,
            (
                member_id,
                operation_date,
                status,
                available,
                shift,
                source_reference,
                organization_id,
            ),
        )


def _canonical_snapshot(organization_id: str = ORG) -> list[tuple]:
    with db_session() as conn:
        rows = conn.execute(
            """
            SELECT id, workforce_member_id, date, status_code, availability,
                   shift_code, start_time, end_time, notes, source_reference,
                   observed_or_confirmed, updated_at, organization_id
            FROM workforce_day_statuses
            WHERE organization_id = ? ORDER BY id
            """,
            (organization_id,),
        ).fetchall()
    return [tuple(row[key] for key in row.keys()) for row in rows]


def _ready_scenario(driver_count: int = 2):
    planning = _legacy_planning()
    members = [_member(f"WF-LEGACY-{index}") for index in range(driver_count)]
    for index, member_id in enumerate(members):
        _status(member_id, "2026-08-10", shift=f"C{index + 1}")
        _status(
            member_id,
            "2026-08-11",
            status="rest",
            available=0,
            shift="R",
            source_reference=f"Planning:row:{index + 10}",
        )
    return planning, members


def test_preview_uses_only_scoped_canonical_rows_and_is_deterministic():
    planning, members = _ready_scenario()
    foreign = _member("WF-FOREIGN", "other-organization")
    _status(foreign, "2026-08-10", organization_id="other-organization")

    first = bridge.preview(ORG, planning.id)
    second = bridge.preview(ORG, planning.id)

    assert first.ready_to_publish is True
    assert first.rows_total == 4
    assert first.drivers_total == len(members)
    assert first.statuses_count == {"rest": 2, "scheduled": 2}
    assert first.provenance == "LEGACY_CANONICAL"
    assert first.fingerprint == second.fingerprint
    assert first.period_start == "2026-08-10"
    assert first.period_end == "2026-08-16"


def test_bridge_rejects_mergeable_source_and_zero_canonical_rows():
    empty = _legacy_planning()
    with pytest.raises(DriverShiftPlanningPublishBlockedError, match="Nessun turno"):
        bridge.preview(ORG, empty.id)

    member_id = _member("WF-MERGEABLE")
    planning = _legacy_planning(start="2026-08-20", end="2026-08-21")
    _status(member_id, "2026-08-20")
    with db_session() as conn:
        source = conn.execute(
            """
            SELECT workforce_import_id FROM driver_shift_planning_sources
            WHERE driver_shift_planning_id = ? AND organization_id = ?
            """,
            (planning.id, ORG),
        ).fetchone()
        conn.execute(
            """
            INSERT INTO workforce_import_rows (
                organization_id, workforce_import_id, source_sheet,
                source_row_number, source_reference, source_record_key,
                row_kind, operational_date, status_code, availability,
                resolved_workforce_member_id, raw_payload
            ) VALUES (?, ?, 'Planning', 2, 'Planning!2', 'shift:2', 'shift',
                      '2026-08-20', 'scheduled', 1, ?, '{}')
            """,
            (ORG, source["workforce_import_id"], member_id),
        )
    with pytest.raises(DriverShiftPlanningPublishBlockedError, match="multi-source normale"):
        bridge.preview(ORG, planning.id)


def test_publish_writes_legacy_projection_without_touching_canonical_workforce():
    planning, _ = _ready_scenario()
    before = _canonical_snapshot()
    preview = bridge.preview(ORG, planning.id)

    result = bridge.publish(
        ORG, planning.id, preview.planning.version, preview.fingerprint, actor="qa@test"
    )

    assert result.planning.status.value == "ACTIVE"
    assert result.published_rows == 4
    assert _canonical_snapshot() == before
    with db_session() as conn:
        rows = conn.execute(
            """
            SELECT status_code, shift_code, start_time, end_time, station,
                   transporter_id, notes, provenance_type, provenance_summary,
                   selected_source_row_id
            FROM driver_shift_planning_published_rows
            WHERE organization_id = ? AND driver_shift_planning_id = ?
            ORDER BY workforce_member_id, operational_date
            """,
            (ORG, planning.id),
        ).fetchall()
        source_rows = conn.execute(
            "SELECT COUNT(*) AS total FROM workforce_import_rows WHERE organization_id = ?",
            (ORG,),
        ).fetchone()["total"]
        audit = conn.execute(
            """
            SELECT reason, source, after_value FROM workforce_changes
            WHERE organization_id = ? AND entity_id = ? ORDER BY id DESC LIMIT 1
            """,
            (ORG, str(planning.id)),
        ).fetchone()
    assert source_rows == 0
    assert {row["status_code"] for row in rows} == {"scheduled", "rest"}
    assert {row["shift_code"] for row in rows} == {"C1", "C2", "R"}
    assert all(row["start_time"] is None and row["end_time"] is None for row in rows)
    assert all(row["station"] is None and row["transporter_id"] is None for row in rows)
    assert all(row["selected_source_row_id"] is None for row in rows)
    assert all(row["provenance_type"] == "LEGACY_CANONICAL" for row in rows)
    assert all('"provenance_type": "LEGACY_CANONICAL"' in row["provenance_summary"] for row in rows)
    assert all(row["notes"] == "Nota reale" for row in rows)
    assert audit["reason"] == "driver_shift_planning_legacy_published"
    assert audit["source"] == "legacy_canonical_publication_bridge"
    assert preview.fingerprint in audit["after_value"]


def test_canonical_change_after_preview_causes_conflict_and_total_rollback():
    planning, members = _ready_scenario(1)
    preview = bridge.preview(ORG, planning.id)
    with db_session() as conn:
        conn.execute(
            """
            UPDATE workforce_day_statuses SET shift_code = 'CHANGED'
            WHERE organization_id = ? AND workforce_member_id = ? AND date = '2026-08-10'
            """,
            (ORG, members[0]),
        )
    with pytest.raises(DriverShiftPlanningConflictError):
        bridge.publish(ORG, planning.id, preview.planning.version, preview.fingerprint)
    with db_session() as conn:
        assert conn.execute(
            "SELECT COUNT(*) AS total FROM driver_shift_planning_published_rows"
        ).fetchone()["total"] == 0
    assert driver_shift_planning_service.get_driver_shift_planning(
        ORG, planning.id
    ).status.value == "DRAFT"


def test_publish_retry_is_idempotent_and_previous_active_is_superseded():
    with db_session() as conn:
        cursor = conn.execute(
            """
            INSERT INTO driver_shift_plannings (
                organization_id, label, period_start, period_end, status, version,
                created_at, created_by, updated_at, published_at, published_by
            ) VALUES (?, 'Old', '2026-08-10', '2026-08-16', 'ACTIVE', 1,
                      '2026-08-01T00:00:00Z', 'qa@test', '2026-08-01T00:00:00Z',
                      '2026-08-01T00:00:00Z', 'qa@test')
            """,
            (ORG,),
        )
        old_id = int(cursor.lastrowid)
    planning, _ = _ready_scenario(1)
    preview = bridge.preview(ORG, planning.id)
    first = bridge.publish(ORG, planning.id, planning.version, preview.fingerprint)
    second = bridge.publish(ORG, planning.id, planning.version, preview.fingerprint)
    assert first.published_rows == second.published_rows == 2
    assert old_id in first.superseded_planning_ids
    with db_session() as conn:
        assert conn.execute(
            "SELECT COUNT(*) AS total FROM driver_shift_planning_published_rows WHERE driver_shift_planning_id = ?",
            (planning.id,),
        ).fetchone()["total"] == 2
        assert conn.execute(
            "SELECT status FROM driver_shift_plannings WHERE id = ?", (old_id,)
        ).fetchone()["status"] == "SUPERSEDED"


def test_repository_failure_rolls_back_projection_lifecycle_and_audit(monkeypatch):
    planning, _ = _ready_scenario(1)
    preview = bridge.preview(ORG, planning.id)
    before = _canonical_snapshot()

    def fail(*_args, **_kwargs):
        raise RuntimeError("forced failure")

    monkeypatch.setattr(bridge_repository, "_insert_published_rows", fail)
    with pytest.raises(RuntimeError, match="forced failure"):
        bridge.publish(ORG, planning.id, planning.version, preview.fingerprint)
    assert _canonical_snapshot() == before
    assert driver_shift_planning_service.get_driver_shift_planning(
        ORG, planning.id
    ).status.value == "DRAFT"
    with db_session() as conn:
        assert conn.execute(
            "SELECT COUNT(*) AS total FROM workforce_changes WHERE reason = 'driver_shift_planning_legacy_published'"
        ).fetchone()["total"] == 0


def test_distribution_credentials_shared_portal_and_personal_week_need_no_branch():
    planning, _ = _ready_scenario(1)
    preview = bridge.preview(ORG, planning.id)
    bridge.publish(ORG, planning.id, planning.version, preview.fingerprint)

    distribution = driver_shift_distribution_service.prepare_distribution(
        ORG, planning.id, "qa@test"
    )
    credentials = driver_shift_credentials_service.prepare_credentials(
        ORG, distribution.distribution.id, "qa@test"
    )
    portal = driver_shift_portal_service.prepare_portal(
        ORG, distribution.distribution.id, "qa@test"
    )
    initial = credentials.initial_credentials[0]
    portal_token = portal.access_url.split("#token=", 1)[1]
    view, session_token, _ = driver_shift_driver_session_service.login(
        portal_token=portal_token,
        access_code=initial.access_code,
        pin=initial.initial_pin,
        remember_device=False,
        client_ip="127.0.0.1",
    )
    week = driver_shift_driver_session_service.current_shifts(session_token)

    assert distribution.summary.recipients_total == 1
    assert credentials.summary.credentials_ready == 1
    assert view.driver_name == "Driver WF-LEGACY-0"
    assert week.days[0].shifts[0].raw_shift_code == "C1"
    assert week.days[1].shifts[0].availability is False
    assert week.days[0].shifts[0].station is None


def test_api_exposes_explicit_preview_and_publish_with_409_on_stale_fingerprint(monkeypatch):
    monkeypatch.setattr(
        "app.plugins.workforce.interfaces.router.ensure_real_data_write_allowed",
        lambda: None,
    )
    planning, members = _ready_scenario(1)
    client = TestClient(app)
    response = client.get(f"{BASE}/driver-shift-plannings/{planning.id}/legacy-preview")
    assert response.status_code == 200
    payload = response.json()
    assert payload["rows_total"] == 2
    assert payload["provenance"] == "LEGACY_CANONICAL"
    with db_session() as conn:
        conn.execute(
            "UPDATE workforce_day_statuses SET status_code='rest' WHERE workforce_member_id=?",
            (members[0],),
        )
    stale = client.post(
        f"{BASE}/driver-shift-plannings/{planning.id}/legacy-publish",
        json={
            "expected_version": planning.version,
            "expected_fingerprint": payload["fingerprint"],
        },
    )
    assert stale.status_code == 409
    refreshed = client.get(
        f"{BASE}/driver-shift-plannings/{planning.id}/legacy-preview"
    ).json()
    published = client.post(
        f"{BASE}/driver-shift-plannings/{planning.id}/legacy-publish",
        json={
            "expected_version": planning.version,
            "expected_fingerprint": refreshed["fingerprint"],
        },
    )
    assert published.status_code == 200
    assert published.json()["planning"]["status"] == "ACTIVE"


def test_47800_row_preview_and_publish_are_batch_based_and_under_target():
    driver_count = 200
    day_count = 239
    start = date(2026, 1, 1)
    planning = _legacy_planning(start="2026-01-01", end="2026-08-27")
    with db_session() as conn:
        conn.executemany(
            """
            INSERT INTO workforce_members (
                external_identifier, display_name, capabilities, active,
                source_reference, created_at, updated_at, organization_id
            ) VALUES (?, ?, '[]', 1, 'performance', '2026-01-01T00:00:00Z',
                      '2026-01-01T00:00:00Z', ?)
            """,
            [(f"PERF-{index}", f"Driver {index}", ORG) for index in range(driver_count)],
        )
        member_rows = conn.execute(
            "SELECT id FROM workforce_members WHERE organization_id = ? ORDER BY id",
            (ORG,),
        ).fetchall()
        rows = []
        for member in member_rows:
            for day_index in range(day_count):
                rows.append(
                    (
                        member["id"],
                        (start + timedelta(days=day_index)).isoformat(),
                        "scheduled",
                        1,
                        "C1",
                        f"Planning:row:{member['id']}",
                        ORG,
                    )
                )
        conn.executemany(
            """
            INSERT INTO workforce_day_statuses (
                workforce_member_id, date, status_code, availability, shift_code,
                source_reference, observed_or_confirmed, updated_at, organization_id
            ) VALUES (?, ?, ?, ?, ?, ?, 'imported', '2026-08-08T10:23:10Z', ?)
            """,
            rows,
        )
    before_count = len(_canonical_snapshot())
    started = perf_counter()
    preview = bridge.preview(ORG, planning.id)
    publication = bridge.publish(
        ORG, planning.id, planning.version, preview.fingerprint, actor="performance@test"
    )
    elapsed = perf_counter() - started
    assert preview.rows_total == publication.published_rows == 47_800
    assert len(_canonical_snapshot()) == before_count == 47_800
    assert elapsed < 10
