from datetime import date, timedelta

from fastapi.testclient import TestClient

from app.core.database import db_session
from app.main import app

client = TestClient(app)
BASE = "/api/plugins/fleet/v1"
JOURNAL = f"{BASE}/journal"
CONTROL = "/api/fleet/journal-control-room"


def asset():
    return client.post(f"{BASE}/assets", json={
        "external_identifier": "JCR-001", "plate": "JC001AA",
        "category": "Furgone", "status": "active",
        "availability": "available", "capabilities": [],
    }).json()


def open_session(vehicle, operation="check_in", driver="Mario Rossi"):
    response = client.post(f"{JOURNAL}/sessions", json={
        "operation_type": operation, "plate": vehicle["plate"],
        "declared_driver_identifier": driver,
        "operational_shift": "morning" if operation == "check_out" else None,
    })
    assert response.status_code == 201
    return response.json()


def complete(opened, anomaly=False):
    response = client.post(
        f"{JOURNAL}/sessions/{opened['id']}/complete",
        headers={"X-Journal-Token": opened["token"]},
        json={
            "odometer_km": 42500, "fuel_percentage": 45,
            "cleanliness_status": "compliant",
            "anomaly_present": anomaly,
            "anomaly_description": "Graffio fiancata" if anomaly else None,
            "operational_note": "Controllo concluso",
            "equipment": [
                {"code": "telepass", "status": "present"},
                {"code": "phone", "status": "present"},
                {"code": "keys", "status": "present"},
                {"code": "fuel_card", "status": "present"},
            ],
            "client_submission_id": f"jcr-{opened['id']}",
            "timezone": "Europe/Rome",
        },
    )
    assert response.status_code == 200
    return response.json()


def test_list_detail_links_and_no_duplication():
    vehicle = asset()
    out = complete(open_session(vehicle, "check_out"), False)
    returned = complete(open_session(vehicle, "check_in"), True)
    damage = client.post("/api/fleet/damage-cases", json={
        "vehicle_id": vehicle["id"], "source_movement_id": returned["id"],
        "occurred_at": returned["occurred_at"], "origin": "journal",
        "description": "Graffio fiancata", "severity": "media",
        "vehicle_operational_status": "disponibile_con_limitazioni",
    })
    assert damage.status_code == 201
    incomplete = open_session(vehicle, "check_out", "Driver Parziale")

    payload = client.get(CONTROL).json()
    assert payload["total"] == 3
    assert payload["summary"]["check_outs"] == 2
    assert payload["summary"]["check_ins"] == 1
    assert payload["summary"]["with_anomalies"] == 1
    assert payload["summary"]["incomplete"] == 1
    anomaly = next(item for item in payload["items"] if item["id"] == returned["id"])
    assert anomaly["status"] == "con_anomalia"
    assert anomaly["operational_document_id"].startswith("JM-")
    assert anomaly["receipt_url"].endswith(f"/{returned['id']}/receipt")
    assert anomaly["damage_case_id"]
    assert anomaly["damage_case_number"]
    assert next(item for item in payload["items"] if item["id"] == incomplete["id"])["status"] == "in_progress"
    detail = client.get(f"{CONTROL}/{out['id']}")
    assert detail.status_code == 200
    assert len(detail.json()["equipment"]) == 4
    with db_session() as conn:
        assert conn.execute("SELECT COUNT(*) FROM asset_movements").fetchone()[0] == 2


def test_combined_filters_search_vehicle_and_missing_detail():
    vehicle = asset()
    movement = complete(open_session(vehicle, "check_in", "Driver Ricerca"), True)
    assert client.get(CONTROL, params={
        "search": "graffio", "operation_type": "check_in",
        "anomaly": "with", "period": "today", "vehicle_id": vehicle["id"],
    }).json()["items"][0]["id"] == movement["id"]
    assert client.get(CONTROL, params={"search": "inesistente"}).json()["items"] == []
    assert client.get(f"{CONTROL}/missing").status_code == 404


def test_manager_session_link_recovery_and_lifecycle():
    vehicle = asset()
    operational_day = client.get(CONTROL).json()["context"]["operational_date"]
    generated_response = client.post(f"{CONTROL}/sessions", json={
        "operation_type": "check_in",
        "plate": vehicle["plate"],
        "declared_driver_identifier": "Driver Demo",
        "scheduled_date": operational_day,
        "scheduled_time": "18:45",
    })
    assert generated_response.status_code == 201
    generated = generated_response.json()
    assert generated["lifecycle_status"] == "generated"
    assert generated["source"] == "fleet_manager"
    assert generated["link_path"] == f"/app/journal/?session={generated['id']}"
    assert vehicle["plate"] not in generated["link_path"]
    assert "Driver" not in generated["link_path"]
    assert "token" not in generated

    listed = client.get(CONTROL).json()
    procedure = next(item for item in listed["items"] if item["id"] == generated["id"])
    assert procedure["status"] == "generated"
    assert listed["summary"]["incomplete"] == 1

    opened_response = client.get(f"{JOURNAL}/sessions/{generated['id']}")
    assert opened_response.status_code == 200
    opened = opened_response.json()
    assert opened["lifecycle_status"] == "opened"
    assert opened["declared_driver_identifier"] == "Driver Demo"
    assert opened["plate_snapshot"] == vehicle["plate"]
    assert opened["operation_type"] == "check_in"
    assert opened["scheduled_at"] == f"{operational_day}T18:45:00"
    assert opened["token"]

    progress = client.post(
        f"{JOURNAL}/sessions/{generated['id']}/progress",
        headers={"X-Journal-Token": opened["token"]},
    )
    assert progress.status_code == 200
    assert progress.json()["lifecycle_status"] == "in_progress"
    assert client.get(CONTROL).json()["items"][0]["status"] == "in_progress"

    receipt = complete(opened)
    assert receipt["plate_snapshot"] == vehicle["plate"]
    completed = client.get(CONTROL).json()["items"][0]
    assert completed["status"] == "completed"
    assert completed["source"] == "fleet_manager"


def test_control_room_is_current_day_plus_relevant_previous_carryover():
    vehicle = asset()
    current = date.fromisoformat(client.get(CONTROL).json()["context"]["operational_date"])
    current_open = open_session(vehicle, "check_out", "Driver Oggi")
    previous_open = open_session(vehicle, "check_in", "Driver Ieri")
    old_open = open_session(vehicle, "check_out", "Driver Storico")
    old_completed = complete(open_session(vehicle, "check_in", "Driver Completo"))
    with db_session() as conn:
        conn.execute("UPDATE journal_sessions SET operational_date=? WHERE id=?", ((current - timedelta(days=1)).isoformat(), previous_open["id"]))
        conn.execute("UPDATE journal_sessions SET operational_date=? WHERE id=?", ((current - timedelta(days=2)).isoformat(), old_open["id"]))
        conn.execute("UPDATE journal_sessions SET operational_date=? WHERE id=(SELECT session_id FROM asset_movements WHERE id=?)", ((current - timedelta(days=2)).isoformat(), old_completed["id"]))

    payload = client.get(CONTROL).json()
    identifiers = {item["id"] for item in payload["items"]}
    assert current_open["id"] in identifiers
    assert previous_open["id"] in identifiers
    assert old_open["id"] not in identifiers
    assert old_completed["id"] not in identifiers
    assert payload["summary"]["incomplete"] == 1

    archive_day = (current - timedelta(days=2)).isoformat()
    historical = client.get("/api/fleet/journal-archive/day", params={
        "date": archive_day, "plate": vehicle["plate"], "driver": "Completo",
    }).json()
    assert [item["id"] for item in historical["items"]] == [old_completed["id"]]
    assert historical["summary"]["total"] == 2


def test_managed_session_uses_organization_timezone_at_operational_boundary():
    vehicle = asset()
    response = client.post(f"{CONTROL}/sessions", json={
        "operation_type": "check_in", "plate": vehicle["plate"],
        "declared_driver_identifier": "Driver Notturno",
        "scheduled_date": "2026-08-02", "scheduled_time": "03:20",
    })
    assert response.status_code == 201
    assert response.json()["operational_date"] == "2026-08-01"


def test_live_summary_exposes_expected_not_started_and_objective_late_state():
    vehicle = asset()
    operational_day = client.get(CONTROL).json()["context"]["operational_date"]
    response = client.post(f"{CONTROL}/sessions", json={
        "operation_type": "check_out", "plate": vehicle["plate"],
        "declared_driver_identifier": "Driver Atteso",
        "scheduled_date": operational_day, "scheduled_time": "04:01",
    })
    assert response.status_code == 201
    payload = client.get(CONTROL).json()
    item = next(entry for entry in payload["items"] if entry["id"] == response.json()["id"])
    assert item["status"] == "generated"
    assert item["is_late"] is True
    assert payload["summary"]["expected_drivers"] == 0
    assert payload["completion"]["planning_id"] is None
    assert payload["summary"]["not_started"] == 1
    assert payload["summary"]["late"] == 1
    filtered = client.get(CONTROL, params={"live_status": "late"}).json()
    assert [entry["id"] for entry in filtered["items"]] == [response.json()["id"]]
    assert filtered["summary"] == payload["summary"]


def test_archive_day_is_chronological_with_stable_operation_tie_breaking():
    vehicle = asset()
    returned = complete(open_session(vehicle, "check_in", "Driver Rientro"))
    checkout_b = complete(open_session(vehicle, "check_out", "Driver B"))
    checkout_a = complete(open_session(vehicle, "check_out", "Driver A"))
    operational_day = client.get(CONTROL).json()["context"]["operational_date"]
    with db_session() as conn:
        for movement_id in (returned["id"], checkout_b["id"], checkout_a["id"]):
            conn.execute(
                "UPDATE asset_movements SET occurred_at=? WHERE id=?",
                (f"{operational_day}T08:10:00+00:00", movement_id),
            )
    items = client.get("/api/fleet/journal-archive/day", params={
        "date": operational_day,
    }).json()["items"]
    checkout_ids = sorted([checkout_a["id"], checkout_b["id"]])
    assert [item["id"] for item in items] == [*checkout_ids, returned["id"]]


def test_manager_session_requires_real_vehicle_and_valid_shared_id():
    response = client.post(f"{CONTROL}/sessions", json={
        "operation_type": "check_out",
        "plate": "MISSING",
        "declared_driver_identifier": "Driver Demo",
        "scheduled_date": "2026-07-30",
        "scheduled_time": "08:00",
    })
    assert response.status_code == 404
    assert client.get(f"{JOURNAL}/sessions/not-a-session").status_code == 404


def test_existing_completed_movement_overrides_migrated_lifecycle_default():
    vehicle = asset()
    opened = open_session(vehicle, "check_in")
    complete(opened, anomaly=True)
    with db_session() as conn:
        conn.execute(
            "UPDATE journal_sessions SET lifecycle_status = 'in_progress' WHERE id = ?",
            (opened["id"],),
        )
    procedure = client.get(CONTROL).json()["items"][0]
    assert procedure["status"] == "con_anomalia"
    assert procedure["operational_document_id"]


def create_shared(vehicle, operation="check_out", name="  mARIO ", surname=" rOSSI  "):
    response = client.post(f"{JOURNAL}/sessions/shared", json={
        "driver_name": name,
        "driver_surname": surname,
        "vehicle_plate": f" {vehicle['plate'].lower()} ",
        "procedure_type": operation,
    })
    assert response.status_code == 201
    return response.json()


def test_shared_link_session_normalization_lifecycle_completion_and_histories():
    vehicle = asset()
    opened = create_shared(vehicle)
    assert opened["driver_name"] == "Mario"
    assert opened["driver_surname"] == "Rossi"
    assert opened["asset"]["plate"] == vehicle["plate"]
    assert opened["lifecycle_status"] == "opened"
    with db_session() as conn:
        stored = conn.execute(
            "SELECT * FROM journal_sessions WHERE id = ?",
            (opened["session_id"],),
        ).fetchone()
    assert stored["source"] == "shared_link"
    assert stored["driver_name"] == "Mario"
    assert stored["driver_surname"] == "Rossi"
    assert stored["opened_at"]
    assert stored["operational_date"]

    progress = client.post(
        f"{JOURNAL}/sessions/{opened['session_id']}/progress",
        headers={"X-Journal-Token": opened["token"]},
    )
    assert progress.status_code == 200
    assert progress.json()["lifecycle_status"] == "in_progress"

    compatible = {"id": opened["session_id"], "token": opened["token"]}
    movement = complete(compatible)
    assert movement["operation_type"] == "check_out"
    room = client.get(CONTROL).json()
    item = next(entry for entry in room["items"] if entry["id"] == movement["id"])
    assert item["origin"] == "Shared link"
    assert item["declared_driver_identifier"] == "Mario Rossi"
    assert item["status"] == "completed"
    assert client.get(CONTROL, params={"search": "mario rossi"}).json()["total"] == 1
    history = client.get(f"{JOURNAL}/vehicles/{vehicle['id']}/history").json()
    assert history["movements"][0]["declared_driver_identifier"] == "Mario Rossi"


def test_shared_link_smart_warnings_are_non_blocking_and_persisted():
    vehicle = asset()
    first = create_shared(vehicle)
    complete({"id": first["session_id"], "token": first["token"]})

    duplicate = create_shared(vehicle, "check_out", "Luigi", "Bianchi")
    codes = {warning["code"] for warning in duplicate["warnings"]}
    assert {"duplicate_checkout_today", "consecutive_checkout"} <= codes
    warning_check = client.post(
        f"{JOURNAL}/sessions/{duplicate['session_id']}/warnings",
        headers={"X-Journal-Token": duplicate["token"]},
        json={"odometer_km": 100},
    )
    assert warning_check.status_code == 200
    assert "odometer_decreased" in {
        warning["code"] for warning in warning_check.json()["warnings"]
    }
    completed = complete(
        {"id": duplicate["session_id"], "token": duplicate["token"]}
    )
    assert completed["id"]
    room_item = next(
        item for item in client.get(CONTROL).json()["items"]
        if item["id"] == completed["id"]
    )
    assert room_item["warnings"]


def test_shared_return_without_checkout_warning_and_schema_migration_idempotency():
    vehicle = asset()
    returned = create_shared(vehicle, "check_in", "Anna", "Verdi")
    assert "return_without_checkout" in {
        warning["code"] for warning in returned["warnings"]
    }
    from app.plugins.fleet.journal.infrastructure.repository import init_schema
    init_schema()
    init_schema()
    with db_session() as conn:
        columns = {
            row["name"]
            for row in conn.execute("PRAGMA table_info(journal_sessions)").fetchall()
        }
    assert {
        "source", "lifecycle_status", "driver_name", "driver_surname",
        "warnings_json", "operational_date",
    } <= columns
