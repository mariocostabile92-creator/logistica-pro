from copy import deepcopy

import pytest
from starlette.testclient import TestClient

from app.core.database import db_session
from app.main import app
from app.plugins.dsp_workspace.application.service import (
    daily_operations_snapshot,
)


DAY = "2026-08-09"
NOW = f"{DAY}T08:00:00+00:00"


def _member(
    organization_id: str,
    identifier: str,
    name: str,
    *,
    status: str = "available",
    station: str = "DLO1",
) -> int:
    with db_session() as conn:
        member_id = int(conn.execute(
            """
            INSERT INTO workforce_members (
                organization_id, external_identifier, display_name, first_name,
                last_name, role, employment_type, station, capabilities, active,
                source_reference, created_at, updated_at
            ) VALUES (?, ?, ?, ?, '', 'driver', 'full_time', ?, '[]', 1,
                      'dsp-test', ?, ?)
            """,
            (organization_id, identifier, name, name, station, NOW, NOW),
        ).lastrowid)
        conn.execute(
            """
            INSERT INTO workforce_day_statuses (
                workforce_member_id, date, status_code, availability,
                source_reference, observed_or_confirmed, updated_at,
                organization_id
            ) VALUES (?, ?, ?, ?, 'dsp-test', 'manual', ?, ?)
            """,
            (
                member_id,
                DAY,
                status,
                int(status in {"available", "scheduled", "available_limited"}),
                NOW,
                organization_id,
            ),
        )
    return member_id


def _asset(
    organization_id: str,
    plate: str,
    *,
    availability: str = "available",
    model: str = "Ford Transit",
) -> int:
    with db_session() as conn:
        return int(conn.execute(
            """
            INSERT INTO fleet_assets (
                organization_id, external_identifier, plate, category,
                status, availability, notes, capabilities, created_at, updated_at
            ) VALUES (?, ?, ?, ?, 'active', ?, NULL, '[]', ?, ?)
            """,
            (organization_id, f"ASSET-{plate}", plate, model, availability, NOW, NOW),
        ).lastrowid)


def _planning(
    organization_id: str,
    status: str,
    *,
    assignments: list[dict] | None = None,
    updated_at: str = NOW,
) -> int:
    with db_session() as conn:
        planning_import = int(conn.execute(
            """
            INSERT INTO imports (
                organization_id, dataset_type, original_filename, imported_at,
                column_mapping, normalized_rows
            ) VALUES (?, 'planning', 'planning.csv', ?, '{}', '[]')
            """,
            (organization_id, NOW),
        ).lastrowid)
        fleet_import = int(conn.execute(
            """
            INSERT INTO imports (
                organization_id, dataset_type, original_filename, imported_at,
                column_mapping, normalized_rows
            ) VALUES (?, 'fleet', 'fleet.csv', ?, '{}', '[]')
            """,
            (organization_id, NOW),
        ).lastrowid)
        planning_id = int(conn.execute(
            """
            INSERT INTO plannings (
                organization_id, operation_date, station,
                source_planning_import_id, source_fleet_import_id, status,
                version, reserve_threshold, configuration, summary, conflicts,
                generation_metadata, created_at, updated_at
            ) VALUES (?, ?, 'DLO1', ?, ?, ?, 1, 1, '{}', '{}', '[]', '{}', ?, ?)
            """,
            (
                organization_id,
                DAY,
                planning_import,
                fleet_import,
                status,
                NOW,
                updated_at,
            ),
        ).lastrowid)
        for index, item in enumerate(assignments or []):
            conn.execute(
                """
                INSERT INTO assignments (
                    planning_id, operation_date, station, route_id, cycle_or_wave,
                    driver_id, driver_name, vehicle_id, plate, assignment_status,
                    assignment_source, confidence, reasons, data_used, warnings,
                    alternatives, manual_override, confirmed, created_at, updated_at
                ) VALUES (?, ?, 'DLO1', ?, ?, ?, ?, ?, ?, ?, 'manual', 1.0,
                          '[]', '[]', '[]', '[]', 0, 1, ?, ?)
                """,
                (
                    planning_id,
                    DAY,
                    item.get("route", f"R-{index + 1}"),
                    item.get("wave"),
                    item.get("driver_id"),
                    item.get("driver_name"),
                    item.get("vehicle_id") or item.get("plate"),
                    item.get("plate"),
                    item.get("assignment_status", "confirmed"),
                    NOW,
                    NOW,
                ),
            )
    return planning_id


def _snapshot(organization_id: str = "org-a"):
    return daily_operations_snapshot(
        operation_date=DAY,
        organization_id=organization_id,
    )


def _standard_data(
    organization_id: str = "org-a",
    *,
    workforce_status: str = "available",
    fleet_status: str = "available",
):
    member_id = _member(
        organization_id,
        "DRV-1",
        "Mario Driver",
        status=workforce_status,
    )
    asset_id = _asset(
        organization_id,
        "AA001AA",
        availability=fleet_status,
    )
    planning_id = _planning(
        organization_id,
        "published",
        assignments=[{
            "driver_id": "DRV-1",
            "driver_name": "Legacy Name",
            "plate": "AA001AA",
            "route": "R-1",
            "wave": "W-1",
        }],
    )
    return member_id, asset_id, planning_id


def test_published_planning_is_selected_before_confirmed():
    published = _planning("org-a", "published")
    _planning("org-a", "confirmed")
    assert _snapshot().planning.planning_id == published


def test_confirmed_planning_is_fallback():
    confirmed = _planning("org-a", "confirmed")
    assert _snapshot().planning.planning_id == confirmed


def test_draft_planning_is_ignored():
    _planning("org-a", "draft")
    assert _snapshot().planning.available is False


def test_generated_and_ready_plannings_are_ignored():
    _planning("org-a", "generated")
    _planning("org-a", "ready")
    assert _snapshot().planning.available is False


def test_superseded_planning_is_ignored():
    _planning("org-a", "superseded")
    assert _snapshot().planning.available is False


def test_no_planning_is_a_valid_empty_snapshot():
    result = _snapshot()
    assert result.planning.available is False
    assert result.rows == []
    assert result.signals == []
    assert result.sources["planning"].status == "no_authoritative_planning"


def test_assignment_builds_compact_operational_row():
    _standard_data()
    row = _snapshot().rows[0]
    assert (row.route, row.wave) == ("R-1", "W-1")
    assert row.vehicle.model == "Ford Transit"


def test_driver_resolution_uses_workforce_external_identifier():
    member_id, _, _ = _standard_data()
    row = _snapshot().rows[0]
    assert row.driver.workforce_member_id == member_id
    assert row.driver.name == "Mario Driver"


def test_vehicle_resolution_uses_shared_planning_vehicle_adapter():
    _, asset_id, _ = _standard_data()
    row = _snapshot().rows[0]
    assert row.vehicle.fleet_asset_id == asset_id
    assert row.vehicle.plate == "AA001AA"


def test_driver_without_vehicle_signal():
    _member("org-a", "DRV-1", "Mario Driver")
    _planning("org-a", "published", assignments=[{
        "driver_id": "DRV-1", "driver_name": "Mario Driver", "route": "R-1",
    }])
    result = _snapshot()
    assert "DRIVER_WITHOUT_VEHICLE" in result.rows[0].attention_codes
    assert result.signals[0].severity == "critical"


def test_driver_not_available_signal_uses_workforce_decision():
    _standard_data(workforce_status="holiday")
    result = _snapshot()
    assert "DRIVER_NOT_AVAILABLE" in result.rows[0].attention_codes
    assert any(item.source == "workforce" for item in result.signals)


def test_vehicle_not_available_signal_uses_fleet_state():
    _standard_data(fleet_status="in_officina")
    result = _snapshot()
    assert "VEHICLE_NOT_AVAILABLE" in result.rows[0].attention_codes
    assert any(item.fleet_asset_id for item in result.signals)


def test_unknown_driver_identifier_does_not_name_match():
    _member("org-a", "DRV-CANONICAL", "Same Name")
    _asset("org-a", "AA001AA")
    _planning("org-a", "published", assignments=[{
        "driver_id": "Same Name", "driver_name": "Same Name", "plate": "AA001AA",
    }])
    row = _snapshot().rows[0]
    assert row.driver.workforce_member_id is None
    assert _snapshot().sources["workforce"].partial is True


def test_unknown_vehicle_identifier_does_not_false_match():
    _member("org-a", "DRV-1", "Mario Driver")
    _asset("org-a", "AA001AA")
    _planning("org-a", "published", assignments=[{
        "driver_id": "DRV-1", "driver_name": "Mario Driver", "plate": "XX999XX",
    }])
    result = _snapshot()
    assert result.rows[0].vehicle.fleet_asset_id is None
    assert result.sources["fleet"].partial is True


def test_planning_isolation_excludes_other_organization():
    own = _planning("org-a", "confirmed")
    _planning("org-b", "published")
    assert _snapshot("org-a").planning.planning_id == own


def test_workforce_isolation_excludes_same_identifier_in_other_organization():
    own_member = _member("org-a", "DRV-1", "Driver A")
    _member("org-b", "DRV-1", "Driver B")
    _asset("org-a", "AA001AA")
    _planning("org-a", "published", assignments=[{
        "driver_id": "DRV-1", "driver_name": "Wrong", "plate": "AA001AA",
    }])
    row = _snapshot("org-a").rows[0]
    assert row.driver.workforce_member_id == own_member
    assert row.driver.name == "Driver A"


def test_fleet_isolation_excludes_same_plate_in_other_organization():
    own_asset = _asset("org-a", "AA001AA", availability="available")
    _asset("org-b", "AA001AA", availability="unavailable")
    _member("org-a", "DRV-1", "Driver A")
    _planning("org-a", "published", assignments=[{
        "driver_id": "DRV-1", "driver_name": "Driver A", "plate": "AA001AA",
    }])
    row = _snapshot("org-a").rows[0]
    assert row.vehicle.fleet_asset_id == own_asset
    assert row.fleet.availability == "available"


def test_client_supplied_organization_cannot_change_tenant():
    _standard_data("test-organization")
    _planning("org-b", "published")
    response = TestClient(app).get(
        f"/api/dsp-workspace/daily-snapshot?operation_date={DAY}&organization_id=org-b"
    )
    assert response.status_code == 200
    assert response.json()["planning"]["available"] is True
    assert response.json()["rows"][0]["driver"]["name"] == "Mario Driver"


def test_snapshot_does_not_generate_convocations(monkeypatch):
    _standard_data()
    called = False

    def forbidden(*args, **kwargs):
        nonlocal called
        called = True
        raise AssertionError("convocations must not be generated")

    monkeypatch.setattr(
        "app.services.planning_operations_service.ensure_convocations",
        forbidden,
    )
    _snapshot()
    assert called is False


def _table_rows(table: str) -> list[dict]:
    with db_session() as conn:
        return [dict(row) for row in conn.execute(
            f"SELECT * FROM {table} ORDER BY 1"
        ).fetchall()]


def test_snapshot_does_not_modify_planning():
    _standard_data()
    tables = ("plannings", "assignments", "planning_events", "planning_convocations")
    before = {table: deepcopy(_table_rows(table)) for table in tables}
    _snapshot()
    assert {table: _table_rows(table) for table in tables} == before


def test_snapshot_does_not_modify_workforce_or_fleet():
    _standard_data()
    tables = (
        "workforce_members", "workforce_day_statuses", "workforce_changes",
        "fleet_assets", "fleet_asset_events",
    )
    before = {table: deepcopy(_table_rows(table)) for table in tables}
    _snapshot()
    assert {table: _table_rows(table) for table in tables} == before


def test_assignments_have_deterministic_route_order():
    _member("org-a", "DRV-1", "Driver A")
    _asset("org-a", "AA001AA")
    _planning("org-a", "published", assignments=[
        {"driver_id": "DRV-1", "plate": "AA001AA", "route": "R-30"},
        {"driver_id": "DRV-1", "plate": "AA001AA", "route": "R-10"},
        {"driver_id": "DRV-1", "plate": "AA001AA", "route": "R-20"},
    ])
    rows = _snapshot().rows
    assert [row.route for row in rows] == ["R-10", "R-20", "R-30"]


def test_latest_published_id_is_deterministic_tie_break():
    _planning("org-a", "published")
    latest = _planning("org-a", "published")
    assert _snapshot().planning.planning_id == latest


@pytest.mark.parametrize("source", ["workforce", "fleet"])
def test_source_failure_degrades_to_partial_without_losing_planning(monkeypatch, source):
    _standard_data()
    target = (
        "app.plugins.dsp_workspace.application.service.foundation_snapshot"
        if source == "workforce"
        else "app.plugins.dsp_workspace.application.service.repository.compact_fleet_assets"
    )
    monkeypatch.setattr(target, lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("down")))
    result = _snapshot()
    assert result.planning.available is True
    assert len(result.rows) == 1
    assert result.sources[source].available is False
    assert result.partial is True


def test_planning_failure_returns_a_valid_partial_snapshot(monkeypatch):
    monkeypatch.setattr(
        "app.plugins.dsp_workspace.application.service.repository."
        "authoritative_planning_snapshot",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("down")),
    )
    result = _snapshot()
    assert result.planning.available is False
    assert result.rows == []
    assert result.sources["planning"].available is False
    assert result.sources["planning"].partial is True
    assert result.partial is True
