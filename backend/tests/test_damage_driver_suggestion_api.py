from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.core.database import db_session
from app.main import app
from app.plugins.fleet.damage.application import service as damage_service


client = TestClient(app)
ENDPOINT = "/api/fleet/damage-cases/driver-suggestion"
ORGANIZATION = "test-organization"
DAY = "2026-08-08"
NOW = f"{DAY}T10:00:00+00:00"


def _member(organization_id: str, identifier: str, name: str) -> int:
    with db_session() as conn:
        return int(conn.execute(
            """
            INSERT INTO workforce_members (
                organization_id, external_identifier, display_name, role,
                capabilities, active, source_reference, created_at, updated_at
            ) VALUES (?, ?, ?, 'driver', '[]', 1, 'suggestion-api-test', ?, ?)
            """,
            (organization_id, identifier, name, NOW, NOW),
        ).lastrowid)


def _asset(organization_id: str, plate: str) -> int:
    with db_session() as conn:
        return int(conn.execute(
            """
            INSERT INTO fleet_assets (
                organization_id, external_identifier, plate, category,
                status, availability, notes, capabilities, created_at, updated_at
            ) VALUES (?, ?, ?, 'Furgone', 'active', 'available', NULL, '[]', ?, ?)
            """,
            (organization_id, f"ASSET-{plate}", plate, NOW, NOW),
        ).lastrowid)


def _movement(
    organization_id: str,
    vehicle_id: int,
    plate: str,
    driver_identifier: str,
) -> None:
    session_id = str(uuid4())
    movement_id = str(uuid4())
    with db_session() as conn:
        conn.execute(
            """
            INSERT INTO journal_sessions (
                id, token_hash, operation_type, asset_id, plate_snapshot,
                declared_driver_identifier, status, created_at, expires_at,
                completed_at, organization_id, source, lifecycle_status,
                operational_date, warnings_json
            ) VALUES (?, 'token', 'check_out', ?, ?, ?, 'completed', ?, ?, ?,
                      ?, 'driver', 'completed', ?, '[]')
            """,
            (
                session_id, vehicle_id, plate, driver_identifier,
                NOW, NOW, NOW, organization_id, DAY,
            ),
        )
        conn.execute(
            """
            INSERT INTO asset_movements (
                id, session_id, schema_version, organization_id,
                operational_unit_id, asset_id, plate_snapshot,
                declared_driver_identifier, operation_type, occurred_at,
                timezone, odometer_km, fuel_percentage, anomaly_present,
                client_submission_id, created_at
            ) VALUES (?, ?, '1.0', ?, 'DLO1', ?, ?, ?, 'check_out', ?,
                      'Europe/Rome', 1000, 80, 0, ?, ?)
            """,
            (
                movement_id, session_id, organization_id, vehicle_id, plate,
                driver_identifier, NOW, f"submission-{movement_id}", NOW,
            ),
        )


def _planning(
    organization_id: str,
    plate: str,
    driver_identifier: str,
    status: str,
) -> None:
    with db_session() as conn:
        planning_import = conn.execute(
            """
            INSERT INTO imports (
                organization_id, dataset_type, original_filename, imported_at,
                column_mapping, normalized_rows
            ) VALUES (?, 'planning', 'planning.csv', ?, '{}', '[]')
            """,
            (organization_id, NOW),
        ).lastrowid
        fleet_import = conn.execute(
            """
            INSERT INTO imports (
                organization_id, dataset_type, original_filename, imported_at,
                column_mapping, normalized_rows
            ) VALUES (?, 'fleet', 'fleet.csv', ?, '{}', '[]')
            """,
            (organization_id, NOW),
        ).lastrowid
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
                organization_id, DAY, planning_import, fleet_import,
                status, NOW, NOW,
            ),
        ).lastrowid)
        conn.execute(
            """
            INSERT INTO assignments (
                planning_id, operation_date, station, route_id,
                driver_id, driver_name, vehicle_id, plate, assignment_status,
                assignment_source, confidence, reasons, data_used, warnings,
                alternatives, manual_override, confirmed, created_at, updated_at
            ) VALUES (?, ?, 'DLO1', ?, ?, ?, ?, ?, 'confirmed', 'manual', 1.0,
                      '[]', '[]', '[]', '[]', 0, 1, ?, ?)
            """,
            (
                planning_id, DAY, f"ROUTE-{planning_id}", driver_identifier,
                driver_identifier, plate, plate, NOW, NOW,
            ),
        )


def _get(vehicle_id: int, **extra):
    return client.get(
        ENDPOINT,
        params={
            "vehicle_id": vehicle_id,
            "operational_date": DAY,
            **extra,
        },
    )


def test_unique_journal_driver_returns_match_and_uses_p63_resolver(monkeypatch):
    member_id = _member(ORGANIZATION, "DRV-J", "Driver Journal")
    vehicle_id = _asset(ORGANIZATION, "SG001AA")
    _movement(ORGANIZATION, vehicle_id, "SG001AA", "DRV-J")
    original = damage_service.resolve_driver_suggestion
    calls = []

    def spy(**values):
        calls.append(values)
        return original(**values)

    monkeypatch.setattr(damage_service, "resolve_driver_suggestion", spy)
    response = _get(vehicle_id)

    assert response.status_code == 200
    assert response.json() == {
        "status": "MATCH",
        "conflict": False,
        "driver": {
            "workforce_member_id": member_id,
            "external_identifier": "DRV-J",
            "display_name": "Driver Journal",
        },
        "source": "journal",
        "evidence": response.json()["evidence"],
        "journal_driver": {
            "workforce_member_id": member_id,
            "external_identifier": "DRV-J",
            "display_name": "Driver Journal",
        },
        "planning_driver": None,
    }
    assert calls == [{
        "organization_id": ORGANIZATION,
        "vehicle_id": vehicle_id,
        "operational_date": DAY,
    }]


@pytest.mark.parametrize("planning_status", ["published", "confirmed"])
def test_authoritative_planning_returns_match(planning_status):
    member_id = _member(ORGANIZATION, "DRV-P", "Driver Planning")
    vehicle_id = _asset(ORGANIZATION, "SG002AA")
    _planning(ORGANIZATION, "SG002AA", "DRV-P", planning_status)

    response = _get(vehicle_id)

    assert response.status_code == 200
    assert response.json()["status"] == "MATCH"
    assert response.json()["source"] == "planning"
    assert response.json()["driver"]["workforce_member_id"] == member_id


def test_draft_planning_returns_not_found():
    _member(ORGANIZATION, "DRV-D", "Driver Draft")
    vehicle_id = _asset(ORGANIZATION, "SG003AA")
    _planning(ORGANIZATION, "SG003AA", "DRV-D", "draft")

    response = _get(vehicle_id)

    assert response.status_code == 200
    assert response.json()["status"] == "NOT_FOUND"
    assert response.json()["driver"] is None
    assert response.json()["conflict"] is False


def test_different_journal_and_planning_drivers_return_conflict():
    journal_id = _member(ORGANIZATION, "DRV-J", "Driver Journal")
    planning_id = _member(ORGANIZATION, "DRV-P", "Driver Planning")
    vehicle_id = _asset(ORGANIZATION, "SG004AA")
    _movement(ORGANIZATION, vehicle_id, "SG004AA", "DRV-J")
    _planning(ORGANIZATION, "SG004AA", "DRV-P", "published")

    response = _get(vehicle_id)

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "CONFLICT"
    assert body["conflict"] is True
    assert body["driver"] is None
    assert body["journal_driver"]["workforce_member_id"] == journal_id
    assert body["planning_driver"]["workforce_member_id"] == planning_id


def test_multiple_journal_drivers_return_ambiguous():
    _member(ORGANIZATION, "DRV-1", "Driver Uno")
    _member(ORGANIZATION, "DRV-2", "Driver Due")
    vehicle_id = _asset(ORGANIZATION, "SG005AA")
    _movement(ORGANIZATION, vehicle_id, "SG005AA", "DRV-1")
    _movement(ORGANIZATION, vehicle_id, "SG005AA", "DRV-2")

    response = _get(vehicle_id)

    assert response.status_code == 200
    assert response.json()["status"] == "AMBIGUOUS"
    assert response.json()["driver"] is None
    assert response.json()["conflict"] is False


def test_no_sources_returns_not_found():
    vehicle_id = _asset(ORGANIZATION, "SG006AA")

    response = _get(vehicle_id)

    assert response.status_code == 200
    assert response.json()["status"] == "NOT_FOUND"
    assert response.json()["driver"] is None


def test_foreign_vehicle_is_not_accessible_and_does_not_leak_driver():
    _member("other-organization", "DRV-X", "Driver Segreto")
    vehicle_id = _asset("other-organization", "SG007AA")
    _movement("other-organization", vehicle_id, "SG007AA", "DRV-X")
    _planning("other-organization", "SG007AA", "DRV-X", "published")

    response = _get(vehicle_id)

    assert response.status_code == 404
    assert response.json() == {"detail": "Veicolo non trovato."}
    assert "Driver Segreto" not in response.text


def test_query_organization_id_cannot_override_authenticated_tenant():
    own_id = _member(ORGANIZATION, "DRV-OWN", "Driver Azienda Corrente")
    vehicle_id = _asset(ORGANIZATION, "SG008AA")
    _movement(ORGANIZATION, vehicle_id, "SG008AA", "DRV-OWN")

    response = _get(vehicle_id, organization_id="other-organization")

    assert response.status_code == 200
    assert response.json()["driver"]["workforce_member_id"] == own_id
    assert response.json()["driver"]["display_name"] == "Driver Azienda Corrente"


def test_suggestion_endpoint_is_read_only_for_damage_cases_and_audit():
    _member(ORGANIZATION, "DRV-RO", "Driver Read Only")
    vehicle_id = _asset(ORGANIZATION, "SG009AA")
    _movement(ORGANIZATION, vehicle_id, "SG009AA", "DRV-RO")
    with db_session() as conn:
        before_cases = conn.execute(
            "SELECT COUNT(*) AS total FROM damage_cases"
        ).fetchone()["total"]
        before_events = conn.execute(
            "SELECT COUNT(*) AS total FROM damage_case_events"
        ).fetchone()["total"]

    response = _get(vehicle_id)

    with db_session() as conn:
        after_cases = conn.execute(
            "SELECT COUNT(*) AS total FROM damage_cases"
        ).fetchone()["total"]
        after_events = conn.execute(
            "SELECT COUNT(*) AS total FROM damage_case_events"
        ).fetchone()["total"]
    assert response.status_code == 200
    assert before_cases == after_cases == 0
    assert before_events == after_events == 0


@pytest.mark.parametrize(
    "params",
    [
        {"vehicle_id": 0, "operational_date": DAY},
        {"vehicle_id": "not-an-id", "operational_date": DAY},
        {"vehicle_id": 1, "operational_date": "not-a-date"},
    ],
)
def test_invalid_query_input_uses_fastapi_validation(params):
    response = client.get(ENDPOINT, params=params)

    assert response.status_code == 422
