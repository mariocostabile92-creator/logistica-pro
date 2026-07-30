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
    generated_response = client.post(f"{CONTROL}/sessions", json={
        "operation_type": "check_in",
        "plate": vehicle["plate"],
        "declared_driver_identifier": "Driver Demo",
        "scheduled_date": "2026-07-30",
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
    assert opened["scheduled_at"] == "2026-07-30T18:45:00"
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
