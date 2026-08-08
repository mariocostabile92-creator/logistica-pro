import json
import sqlite3

import pytest
from fastapi.testclient import TestClient

from app.core.database import db_session
from app.main import app
from app.plugins.fleet.damage.application import driver_attribution_service
from app.plugins.fleet.damage.infrastructure import repository as damage_repository
from app.plugins.workforce.infrastructure import read_repository


client = TestClient(app)
JOURNAL = "/api/plugins/fleet/v1/journal"
DAMAGE = "/api/fleet"
NOW = "2026-08-08T10:00:00+00:00"


def _member(
    identifier: str,
    name: str,
    organization_id: str = "test-organization",
) -> int:
    with db_session() as conn:
        cursor = conn.execute(
            """
            INSERT INTO workforce_members (
                organization_id, external_identifier, display_name, role,
                capabilities, active, source_reference, created_at, updated_at
            ) VALUES (?, ?, ?, 'driver', '[]', 1, 'damage-attribution-test', ?, ?)
            """,
            (organization_id, identifier, name, NOW, NOW),
        )
        return int(cursor.lastrowid)


def _asset(plate: str = "AT010TR") -> dict:
    response = client.post(
        "/api/plugins/fleet/v1/assets",
        json={
            "external_identifier": f"asset-{plate}",
            "plate": plate,
            "category": "van",
            "status": "active",
            "availability": "available",
        },
    )
    assert response.status_code == 201
    return response.json()


def _journal_case(driver_identifier: str) -> dict:
    vehicle = _asset()
    session = client.post(
        f"{JOURNAL}/sessions",
        json={
            "operation_type": "check_in",
            "plate": vehicle["plate"],
            "declared_driver_identifier": driver_identifier,
        },
    ).json()
    completed = client.post(
        f"{JOURNAL}/sessions/{session['id']}/complete",
        headers={"X-Journal-Token": session["token"]},
        json={
            "odometer_km": 42000,
            "fuel_percentage": 45,
            "cleanliness_status": "compliant",
            "anomaly_present": True,
            "anomaly_description": "Danno fiancata",
            "equipment": [
                {"code": "telepass", "status": "present"},
                {"code": "phone", "status": "present"},
                {"code": "keys", "status": "present"},
                {"code": "fuel_card", "status": "present"},
            ],
            "client_submission_id": f"damage-attribution-{driver_identifier}",
            "timezone": "Europe/Rome",
        },
    )
    assert completed.status_code == 200
    candidate = client.get(f"{DAMAGE}/damage-candidates").json()["items"][0]
    response = client.post(
        f"{DAMAGE}/damage-cases",
        json={
            "vehicle_id": vehicle["id"],
            "source_movement_id": candidate["movement_id"],
            "occurred_at": candidate["occurred_at"],
            "origin": "journal",
            "description": "Precompilata dal Journal",
            "severity": "bassa",
            "vehicle_operational_status": "disponibile",
            "actor": "actor-inviato-dal-client",
        },
    )
    assert response.status_code == 201
    return response.json()


def _manual_case() -> dict:
    vehicle = _asset("AT020TR")
    response = client.post(
        f"{DAMAGE}/damage-cases",
        json={
            "vehicle_id": vehicle["id"],
            "occurred_at": "2026-08-08T11:00:00Z",
            "origin": "manual",
            "manual_reason": "Segnalazione Fleet Manager",
            "description": "Danno rilevato in deposito",
            "severity": "media",
            "vehicle_operational_status": "disponibile",
        },
    )
    assert response.status_code == 201
    return response.json()


def test_journal_case_persists_canonical_driver_snapshots_source_and_audit():
    member_id = _member("GDB-001", "Mario Rossi")

    case = _journal_case("GDB-001")

    assert case["driver_workforce_member_id"] == member_id
    assert case["driver_external_identifier_snapshot"] == "GDB-001"
    assert case["driver_name_snapshot"] == "Mario Rossi"
    assert case["driver_attribution_source"] == "journal"
    assert case["driver_attributed_at"]
    assert case["driver_attributed_by"] == "test-harness-administrator"
    assert case["driver_attribution"] == {
        "workforce_member_id": member_id,
        "external_identifier_snapshot": "GDB-001",
        "name_snapshot": "Mario Rossi",
        "source": "journal",
        "attributed_at": case["driver_attributed_at"],
        "attributed_by": "test-harness-administrator",
        "reason": "Attribuzione automatica dalla movimentazione Journal.",
    }
    event = next(
        item
        for item in case["events"]
        if item["event_type"] == "damage_driver_attributed"
    )
    assert event["actor"] == "test-harness-administrator"
    assert json.loads(event["note"]) == {
        "reason": "Attribuzione automatica dalla movimentazione Journal.",
        "source": "journal",
        "workforce_member_id": member_id,
    }


def test_unresolved_journal_driver_keeps_legacy_text_and_null_attribution():
    case = _journal_case("DRIVER-NON-CENSITO")

    assert case["declared_driver"] == "DRIVER-NON-CENSITO"
    assert case["driver_workforce_member_id"] is None
    assert case["driver_external_identifier_snapshot"] is None
    assert case["driver_name_snapshot"] is None
    assert case["driver_attribution_source"] is None
    assert case["driver_attribution"] is None
    assert not any(
        event["event_type"] == "damage_driver_attributed"
        for event in case["events"]
    )


def test_manual_and_existing_legacy_cases_remain_readable_without_attribution():
    case = _manual_case()

    assert case["driver_workforce_member_id"] is None
    assert case["driver_attribution"] is None
    reread = client.get(f"{DAMAGE}/damage-cases/{case['id']}")
    assert reread.status_code == 200
    assert reread.json()["id"] == case["id"]
    assert reread.json()["driver_attribution"] is None


def test_internal_attribution_rejects_driver_from_another_organization():
    case = _manual_case()
    _member("OTHER-001", "Driver altra azienda", "other-organization")
    foreign_member = read_repository.list_members("other-organization")[0]

    with pytest.raises(
        driver_attribution_service.DamageDriverAttributionOrganizationMismatch
    ):
        driver_attribution_service.attribute_driver(
            case["id"],
            foreign_member,
            source="manual",
            actor="server-user",
            reason="Scelta esplicita",
        )

    unchanged = client.get(f"{DAMAGE}/damage-cases/{case['id']}").json()
    assert unchanged["driver_workforce_member_id"] is None


def test_internal_attribution_requires_canonical_workforce_member_not_free_name():
    case = _manual_case()

    with pytest.raises(driver_attribution_service.DamageDriverAttributionInvalid):
        driver_attribution_service.attribute_driver(
            case["id"],
            "Mario Rossi",  # type: ignore[arg-type]
            source="manual",
            actor="server-user",
        )


def test_internal_manual_attribution_uses_canonical_id_and_database_snapshots():
    case = _manual_case()
    member_id = _member("DRV-099", "Giulia Bianchi")
    member = read_repository.list_members("test-organization")[0]

    attributed = driver_attribution_service.attribute_driver(
        case["id"],
        member,
        source="manual",
        actor="server-user",
        reason="Conferma Fleet Manager",
    )

    assert attributed["driver_workforce_member_id"] == member_id
    assert attributed["driver_external_identifier_snapshot"] == "DRV-099"
    assert attributed["driver_name_snapshot"] == "Giulia Bianchi"
    assert attributed["driver_attribution_source"] == "manual"
    events = damage_repository.list_events(case["id"])
    assert events[-1]["event_type"] == "damage_driver_attributed"


def test_damage_schema_migration_is_idempotent_and_preserves_existing_case():
    case = _manual_case()

    damage_repository.init_schema()
    damage_repository.init_schema()

    with db_session() as conn:
        rows = conn.execute(
            "SELECT * FROM damage_cases WHERE id = ?",
            (case["id"],),
        ).fetchall()
        columns = {
            row["name"]
            for row in conn.execute("PRAGMA table_info(damage_cases)").fetchall()
        }
    assert len(rows) == 1
    assert rows[0]["description"] == "Danno rilevato in deposito"
    assert rows[0]["driver_workforce_member_id"] is None
    assert set(damage_repository.DRIVER_ATTRIBUTION_COLUMNS) <= columns

    legacy = sqlite3.connect(":memory:")
    legacy.row_factory = sqlite3.Row
    legacy.execute(
        "CREATE TABLE damage_cases (id INTEGER PRIMARY KEY, description TEXT NOT NULL)"
    )
    legacy.execute(
        "INSERT INTO damage_cases (id, description) VALUES (1, 'Pratica legacy')"
    )
    damage_repository._ensure_driver_attribution_columns(legacy)
    damage_repository._ensure_driver_attribution_columns(legacy)
    migrated = legacy.execute(
        "SELECT * FROM damage_cases WHERE id = 1"
    ).fetchone()
    migrated_columns = {
        row["name"] for row in legacy.execute("PRAGMA table_info(damage_cases)")
    }
    legacy.close()
    assert migrated["description"] == "Pratica legacy"
    assert migrated["driver_workforce_member_id"] is None
    assert set(damage_repository.DRIVER_ATTRIBUTION_COLUMNS) <= migrated_columns
