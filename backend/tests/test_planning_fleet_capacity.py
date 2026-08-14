from fastapi.testclient import TestClient

from app.core.database import db_session
from app.main import app
from app.plugins.dsp_workspace.application.service import daily_operations_snapshot
from app.plugins.fleet.application.daily_capacity_service import (
    classify_availability,
    daily_fleet_capacity,
)


DAY = "2026-08-15"
NOW = "2026-08-14T08:00:00+00:00"
client = TestClient(app)


def _coverage(
    cycle: str,
    segment: str | None,
    forecast: int | None,
    requirement: int | None,
    *,
    authority: str = "AUTHORITATIVE",
    status: str | None = None,
    source: str = "IMPORT",
) -> dict[str, object]:
    return {
        "cycle": cycle,
        "segment": segment,
        "forecast": forecast,
        "raw_forecast": forecast,
        "requirement": requirement,
        "authority_status": authority,
        "status": status or (
            "NO_FORECAST" if forecast is None else "REQUIREMENT_COVERED"
        ),
        "source": source,
    }


def _asset(organization_id: str, plate: str, availability: str) -> int:
    with db_session() as conn:
        return int(conn.execute(
            """
            INSERT INTO fleet_assets (
                organization_id, external_identifier, plate, category,
                status, availability, notes, capabilities, created_at, updated_at
            ) VALUES (?, ?, ?, 'Van', 'active', ?, NULL, '[]', ?, ?)
            """,
            (organization_id, f"ASSET-{plate}", plate, availability, NOW, NOW),
        ).lastrowid)


def test_canonical_availability_classification_supports_current_and_legacy_values():
    for value in ("disponibile", "disponibile_con_limitazioni", "available", "reserve"):
        assert classify_availability(value) == "available"
    for value in ("indisponibile", "unavailable", "fermo"):
        assert classify_availability(value) == "unavailable"
    for value in ("in_manutenzione", "maintenance"):
        assert classify_availability(value) == "maintenance"
    for value in ("in_officina", "workshop"):
        assert classify_availability(value) == "blocked"
    assert classify_availability("legacy-mystery") == "unknown"


def test_daily_snapshot_counts_every_vehicle_once_and_is_organization_scoped():
    values = [
        "disponibile", "disponibile_con_limitazioni", "indisponibile",
        "in_manutenzione", "in_officina", "unknown",
    ]
    for index, value in enumerate(values):
        _asset("org-a", f"AA{index:03d}AA", value)
    _asset("org-b", "BB999BB", "disponibile")

    snapshot = daily_fleet_capacity(
        organization_id="org-a", operational_date=DAY,
    )
    assert snapshot.total_vehicles == 6
    assert snapshot.available_vehicles == 2
    assert snapshot.unavailable_vehicles == 1
    assert snapshot.maintenance_vehicles == 1
    assert snapshot.blocked_vehicles == 1
    assert snapshot.unknown_vehicles == 1


def test_snapshot_is_honest_about_current_date_and_missing_station_scope():
    _asset("org-a", "AA001AA", "disponibile")
    snapshot = daily_fleet_capacity(
        organization_id="org-a",
        operational_date=DAY,
        requested_station="DLO2",
    )
    assert snapshot.operational_date == DAY
    assert snapshot.date_semantics == "CURRENT_OPERATIONAL_STATE"
    assert snapshot.requested_station == "DLO2"
    assert snapshot.station_scope_applied is False


def test_damage_does_not_block_an_asset_that_fleet_keeps_operational():
    asset_id = _asset("org-a", "AA002AA", "disponibile")
    with db_session() as conn:
        conn.execute(
            """
            INSERT INTO damage_cases (
                case_number, vehicle_id, occurred_at, created_at, updated_at,
                origin, description, severity, status,
                vehicle_operational_status
            ) VALUES ('DMG-TEST', ?, ?, ?, ?, 'manuale', 'Graffio', 'media',
                      'aperta', 'disponibile_con_limitazioni')
            """,
            (asset_id, NOW, NOW, NOW),
        )
    snapshot = daily_fleet_capacity(
        organization_id="org-a", operational_date=DAY,
    )
    assert snapshot.available_vehicles == 1
    assert snapshot.blocked_vehicles == 0


def test_open_maintenance_does_not_invent_a_blocking_state():
    asset_id = _asset("org-a", "AA003AA", "disponibile")
    with db_session() as conn:
        conn.execute(
            """
            INSERT INTO fleet_maintenances (
                maintenance_number, vehicle_id, description, maintenance_type,
                status, priority, opened_at, created_at, updated_at
            ) VALUES ('MNT-TEST', ?, 'Tagliando', 'tagliando', 'aperta',
                      'media', ?, ?, ?)
            """,
            (asset_id, NOW, NOW, NOW),
        )
    snapshot = daily_fleet_capacity(
        organization_id="org-a", operational_date=DAY,
    )
    assert snapshot.available_vehicles == 1
    assert snapshot.maintenance_vehicles == 0


def test_vehicle_need_is_null_when_no_effective_forecast_exists():
    _asset("org-a", "AA004AA", "disponibile")
    snapshot = daily_fleet_capacity(
        organization_id="org-a", operational_date=DAY,
    )
    assert snapshot.vehicle_need is None
    assert snapshot.margin is None
    assert snapshot.vehicle_need_status == "NOT_CONFIGURED"
    assert snapshot.missing_requirement_buckets == [
        "NEXT_DAY", "SAME_DAY_A", "SAME_DAY_B_C",
    ]
    assert snapshot.capacity_status == "NEED_NOT_DETERMINABLE"
    assert "da configurare" in snapshot.capacity_message


def test_full_effective_requirement_becomes_complete_vehicle_need(monkeypatch):
    monkeypatch.setattr(
        "app.plugins.fleet.application.daily_capacity_service.repository.availability_counts",
        lambda organization_id: ([{"availability": "disponibile", "count": 120}], NOW),
    )
    snapshot = daily_fleet_capacity(
        organization_id="org-a",
        operational_date=DAY,
        coverage_items=[
            _coverage("NEXT_DAY", None, 70, 77, source="MANUAL"),
            _coverage("SAME_DAY", "A", 20, 22),
            _coverage("SAME_DAY", "B_C", 18, 20),
        ],
    )
    assert snapshot.vehicle_need == 119
    assert snapshot.vehicle_need_status == "COMPLETE"
    assert snapshot.effective_requirement_buckets == [
        "NEXT_DAY", "SAME_DAY_A", "SAME_DAY_B_C",
    ]
    assert snapshot.missing_requirement_buckets == []
    assert snapshot.margin == 1
    assert snapshot.capacity_status == "SUFFICIENT"
    assert snapshot.vehicle_need_rule == "EFFECTIVE_DAILY_OPERATIONAL_REQUIREMENT"


def test_rejected_template_is_excluded_and_known_requirement_is_partial(monkeypatch):
    monkeypatch.setattr(
        "app.plugins.fleet.application.daily_capacity_service.repository.availability_counts",
        lambda organization_id: ([{"availability": "disponibile", "count": 56}], NOW),
    )
    snapshot = daily_fleet_capacity(
        organization_id="org-a",
        operational_date=DAY,
        coverage_items=[
            _coverage(
                "NEXT_DAY", None, None, None,
                authority="REJECTED_TEMPLATE", status="NO_FORECAST",
            ),
            _coverage("SAME_DAY", "A", 20, 22),
            _coverage("SAME_DAY", "B_C", 18, 20),
        ],
    )
    assert snapshot.vehicle_need == 42
    assert snapshot.vehicle_need_status == "PARTIAL"
    assert snapshot.missing_requirement_buckets == ["NEXT_DAY"]
    assert snapshot.margin == 14
    assert snapshot.capacity_message == "Almeno 42 mezzi necessari."


def test_complete_requirement_reports_shortage_against_unchanged_fleet_counts(monkeypatch):
    monkeypatch.setattr(
        "app.plugins.fleet.application.daily_capacity_service.repository.availability_counts",
        lambda organization_id: ([
            {"availability": "disponibile", "count": 56},
            {"availability": "indisponibile", "count": 29},
            {"availability": "in_manutenzione", "count": 1},
        ], NOW),
    )
    snapshot = daily_fleet_capacity(
        organization_id="org-a",
        operational_date=DAY,
        coverage_items=[
            _coverage("NEXT_DAY", None, 70, 77, source="MANUAL"),
            _coverage("SAME_DAY", "A", 20, 22),
            _coverage("SAME_DAY", "B_C", 18, 20),
        ],
    )
    assert snapshot.total_vehicles == 86
    assert snapshot.available_vehicles == 56
    assert snapshot.unavailable_vehicles == 29
    assert snapshot.maintenance_vehicles == 1
    assert snapshot.vehicle_need == 119
    assert snapshot.margin == -63
    assert snapshot.capacity_status == "SHORTAGE"
    assert snapshot.capacity_message == "Mancano 63 mezzi."


def test_planning_without_routes_still_returns_fleet_capacity():
    _asset("test-organization", "AA005AA", "disponibile")
    response = client.get(f"/api/planning/operations?operation_date={DAY}")
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["fleet_capacity"]["total_vehicles"] == 1
    assert payload["fleet_capacity"]["available_vehicles"] == 1
    assert payload["fleet_capacity"]["route_assignments_available"] is False
    assert payload["fleet_capacity"]["assigned_vehicles"] is None
    assert payload["fleet_capacity"]["vehicle_need"] is None
    assert payload["fleet_capacity"]["vehicle_need_status"] == "NOT_CONFIGURED"


def test_dsp_reuses_the_same_fleet_snapshot_without_route_data():
    _asset("org-a", "AA006AA", "in_officina")
    snapshot = daily_operations_snapshot(
        operation_date=DAY, organization_id="org-a",
    )
    assert snapshot.fleet_capacity is not None
    assert snapshot.fleet_capacity["total_vehicles"] == 1
    assert snapshot.fleet_capacity["blocked_vehicles"] == 1
    assert snapshot.fleet_capacity["route_assignments_available"] is False
    assert snapshot.sources["fleet"].status == "available"


def test_capacity_service_uses_one_aggregate_repository_call(monkeypatch):
    calls = []

    def counts(organization_id):
        calls.append(organization_id)
        return ([{"availability": "disponibile", "count": 12}], NOW)

    monkeypatch.setattr(
        "app.plugins.fleet.application.daily_capacity_service.repository.availability_counts",
        counts,
    )
    snapshot = daily_fleet_capacity(
        organization_id="org-a", operational_date=DAY,
    )
    assert calls == ["org-a"]
    assert snapshot.total_vehicles == 12
