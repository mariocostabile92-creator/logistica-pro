from contextlib import nullcontext
import sqlite3

from fastapi.testclient import TestClient

from app.core.database import db_session
from app.main import app
from app.plugins.fleet.vision import repository as vision_repository

client = TestClient(app)
ASSETS = "/api/plugins/fleet/v1/assets"
VISION = "/api/fleet/vision"


def test_vision_uses_a_typed_postgres_organization_filter(monkeypatch):
    executions = []

    class EmptyCursor:
        @staticmethod
        def fetchall():
            return []

    class ProductionEquivalentConnection:
        @staticmethod
        def execute(sql, params=()):
            executions.append((sql, params))
            if "? IS NULL" in sql:
                raise sqlite3.DatabaseError(
                    "could not determine data type of parameter $1"
                )
            return EmptyCursor()

    monkeypatch.setattr(
        vision_repository,
        "db_session",
        lambda: nullcontext(ProductionEquivalentConnection()),
    )

    snapshot = vision_repository.snapshot("production-organization")

    assert snapshot["movements"] == []
    movement_sql, movement_params = next(
        execution for execution in executions if "FROM asset_movements" in execution[0]
    )
    assert "WHERE m.organization_id = ?" in movement_sql
    assert "? IS NULL" not in movement_sql
    assert movement_params == ("production-organization",)


def test_vision_aggregates_existing_modules_without_new_table():
    vehicle = client.post(ASSETS, json={
        "external_identifier": "FVE-001", "plate": "FV001AA",
        "category": "Furgone", "status": "active",
        "availability": "indisponibile", "capabilities": [],
    }).json()
    profile = client.put(f"{ASSETS}/{vehicle['id']}/profile", json={
        "contract_type": "lungo_termine", "company": "Mobility",
        "contract_number": "FVE-LT-1", "monthly_fee": "700",
        "deductible": "500", "included_km": 120000,
        "starts_on": "2026-01-01", "expires_on": "2026-08-20",
        "contract_status": "attivo",
    })
    assert profile.status_code == 200
    damage = client.post("/api/fleet/damage-cases", json={
        "vehicle_id": vehicle["id"], "occurred_at": "2026-07-30T09:00:00Z",
        "origin": "manual", "manual_reason": "Verifica Fleet Vision",
        "description": "Urto laterale", "severity": "alta",
        "vehicle_operational_status": "indisponibile",
    })
    assert damage.status_code == 201
    maintenance = client.post("/api/fleet/maintenances", json={
        "vehicle_id": vehicle["id"], "description": "Ripristino carrozzeria",
        "maintenance_type": "carrozzeria", "status": "in_lavorazione",
        "priority": "alta", "expected_at": "2026-08-10",
    })
    assert maintenance.status_code == 201
    assert client.post("/api/fleet/documents", json={
        "vehicle_id": vehicle["id"], "document_type": "revisione",
        "title": "Revisione mancante", "status": "mancante",
    }).status_code == 201
    assert client.post("/api/fleet/insurance-policies", json={
        "vehicle_id": vehicle["id"], "company": "Sicura",
        "policy_number": "FVE-POL-1", "coverage_type": "kasko",
        "starts_on": "2026-01-01", "expires_on": "2027-01-01",
        "status": "scaduta",
    }).status_code == 201
    assert client.post("/api/fleet/franchises", json={
        "damage_case_id": damage.json()["id"],
    }).status_code == 201
    assert client.post("/api/fleet/rentals", json={
        "vehicle_id": vehicle["id"], "replacement_vehicle": "Van sostitutivo",
        "rental_company": "Rent Fleet", "start_date": "2026-07-30",
        "expected_end_date": "2026-08-15", "reason": "danno", "status": "attivo",
    }).status_code == 201

    response = client.get(VISION, params={"vehicle_id": vehicle["id"]})
    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"] == {
        "operational": 0, "unavailable": 1, "in_maintenance": 0,
        "open_damages": 1, "open_maintenances": 1, "active_rentals": 1,
        "documents_registered": 1, "insurance_policies": 1,
        "open_franchises": 1, "missing_documents": 1, "expired_insurance": 1,
        "expiring_contracts": 1, "journal_anomalies": 0,
        "decisions": 9, "high_priority_decisions": 3,
        "critical_actions": 3, "important_actions": 4,
        "informative_actions": 2,
    }
    insight = payload["items"][0]
    assert insight["contract_type"] == "lungo_termine"
    assert insight["damage_open"] == 1
    assert insight["maintenance_open"] == 1
    assert insight["document_count"] == 1
    assert insight["missing_documents"] == 1
    assert insight["insurance"]["policy_number"] == "FVE-POL-1"
    assert insight["franchises_open"] == 1
    assert insight["franchise_count"] == 1
    assert insight["rentals_active"] == 1
    assert insight["deadlines_imminent"] >= 1
    assert insight["insurance_expired"] == 1
    assert insight["contracts_expiring"] == 1
    assert insight["journal_anomalies"] == 0
    assert {item["source"] for item in insight["timeline"]} >= {
        "damage", "maintenance", "document", "franchise", "rental",
    }
    assert len({item["id"] for item in insight["timeline"]}) == len(insight["timeline"])
    assert {item["key"] for item in insight["insights"]} == {
        "last_use", "last_damage", "last_maintenance", "last_status_change",
        "missing_documents", "imminent_deadlines", "insurance", "contract",
        "active_rental", "open_franchise",
    }
    assert all({"source", "module", "value"} <= item.keys() for item in insight["insights"])
    expected_decisions = {
        "contract_expiring": "media",
        "insurance_expired": "alta",
        "documents_missing": "media",
        "vehicle_not_operational": "alta",
        "damage_open": "alta",
        "maintenance_open": "media",
        "franchise_open": "media",
        "rental_active": "bassa",
        "deadline_soon": "bassa",
    }
    assert {item["rule"]: item["priority"] for item in insight["decisions"]} == expected_decisions
    assert all(
        item["origin"] and item["module"] and item["why"] and item["evidence"]
        for item in insight["decisions"]
    )
    assert len({item["id"] for item in insight["decisions"]}) == len(insight["decisions"])
    expected_actions = {
        "contract_expiring": ("Apri Profilo Contrattuale", "library", "Contratti"),
        "insurance_expired": ("Apri Assicurazione", "insurance", "Documentazione"),
        "documents_missing": ("Apri Documenti", "documents", "Documentazione"),
        "vehicle_not_operational": ("Apri Vehicle Library", "library", "Operatività"),
        "damage_open": ("Apri Danni", "damage", "Operatività"),
        "maintenance_open": ("Apri Manutenzione", "maintenance", "Operatività"),
        "franchise_open": ("Apri Franchigie", "franchises", "Contratti"),
        "rental_active": ("Apri Noleggi", "rentals", "Operatività"),
        "deadline_soon": ("Apri Manutenzioni", "maintenance", "Fleet"),
    }
    decisions_by_id = {item["id"]: item for item in insight["decisions"]}
    assert len(insight["actions"]) == len(insight["decisions"]) == 9
    assert payload["actions"] == insight["actions"]
    assert len({item["id"] for item in insight["actions"]}) == len(insight["actions"])
    for action in insight["actions"]:
        decision = decisions_by_id[action["decision_id"]]
        assert (
            action["title"], action["module"], action["group"]
        ) == expected_actions[decision["rule"]]
        assert action["priority"] == decision["priority"]
        assert action["motivation"] == decision["description"]
        assert action["origin"] == decision["origin"]
        assert action["vehicle_id"] == vehicle["id"]
    assert "risk_score" not in insight
    deadlines = {item["category"]: item for item in payload["upcoming_deadlines"]}
    assert set(deadlines) == {"document", "insurance", "maintenance", "rental"}
    assert deadlines["maintenance"]["count"] == 1
    assert deadlines["maintenance"]["nearest"]["source_id"] == maintenance.json()["id"]
    assert deadlines["rental"]["count"] == 1
    assert deadlines["document"]["count"] == 0
    assert deadlines["insurance"]["count"] == 0
    with db_session() as conn:
        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE '%vision%'"
        ).fetchall()
    assert tables == []


def test_vision_lists_all_assets_and_filters_vehicle():
    first = client.post(ASSETS, json={
        "external_identifier": "FVE-002", "plate": "FV002AA",
        "category": "Van", "status": "active", "availability": "disponibile",
        "capabilities": [],
    }).json()
    client.post(ASSETS, json={
        "external_identifier": "FVE-003", "plate": "FV003AA",
        "category": "Van", "status": "active", "availability": "in_officina",
        "capabilities": [],
    })
    assert client.get(VISION).json()["total"] == 2
    filtered = client.get(VISION, params={"vehicle_id": first["id"]}).json()
    assert filtered["total"] == 1
    assert filtered["items"][0]["plate"] == "FV002AA"
    assert all(action["vehicle_id"] == first["id"] for action in filtered["actions"])


def test_vision_tolerates_legacy_null_status_event_details():
    vehicle = client.post(ASSETS, json={
        "external_identifier": "FVE-LEGACY-NULL", "plate": "FVNULL1",
        "category": "Van", "status": "active", "availability": "disponibile",
        "capabilities": [],
    }).json()
    with db_session() as conn:
        conn.execute(
            """
            INSERT INTO fleet_asset_events (
                asset_id, event_type, occurred_at, actor, details, contract_version
            ) VALUES (?, 'operational_status_changed', ?, 'legacy', 'null', '1.0')
            """,
            (vehicle["id"], "2026-08-02T08:00:00Z"),
        )

    response = client.get(VISION, params={"vehicle_id": vehicle["id"]})

    assert response.status_code == 200
    assert response.json()["items"][0]["operational_status_reason"] is None


def test_vision_keeps_legacy_journal_without_operational_date():
    vehicle = client.post(ASSETS, json={
        "external_identifier": "FVE-LEGACY-GDB", "plate": "FVGDB01",
        "category": None, "status": "active", "availability": "disponibile",
        "capabilities": [],
    }).json()
    with db_session() as conn:
        organization_id = "test-organization"
        conn.execute(
            """INSERT INTO journal_sessions (
                id, token_hash, operation_type, asset_id, plate_snapshot,
                declared_driver_identifier, status, created_at, expires_at,
                completed_at, organization_id, source, lifecycle_status,
                operational_date, warnings_json
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            ("legacy-session", "legacy", "check_out", vehicle["id"], "FVGDB01",
             "DRV-LEGACY", "completed", "2026-08-01T08:00:00Z",
             "2026-08-01T18:00:00Z", "2026-08-01T08:05:00Z",
             organization_id, "driver", "completed", None, "[]"),
        )
        conn.execute(
            """INSERT INTO asset_movements (
                id, session_id, schema_version, organization_id,
                operational_unit_id, asset_id, plate_snapshot,
                declared_driver_identifier, operation_type, occurred_at,
                timezone, odometer_km, fuel_percentage, anomaly_present,
                client_submission_id, created_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            ("legacy-movement", "legacy-session", "1.0", organization_id,
             "legacy", vehicle["id"], "FVGDB01", "DRV-LEGACY", "check_out",
             "2026-08-01T08:05:00Z", "Europe/Rome", 1000, 50, 0,
             "legacy-submission", "2026-08-01T08:05:00Z"),
        )

    response = client.get(VISION, params={"vehicle_id": vehicle["id"]})

    assert response.status_code == 200
    item = response.json()["items"][0]
    assert item["movement_count"] == 1
    assert item["timeline"][0]["operational_date"] is None


def test_fleet_vision_hotfix_assets_are_served_from_real_paths():
    for path in (
        "/app/assets/js/modules/fleet-vision-workspace.js?v=2",
        "/app/assets/js/modules/fleet-vision/aggregator.js",
        "/app/assets/css/fleet-vision-workspace.css?v=2",
        "/app/assets/css/journal-completion.css?v=1",
    ):
        response = client.get(path)
        assert response.status_code == 200, path
    assert client.get("/api/fleet/journal-control-room?limit=200").status_code == 200
