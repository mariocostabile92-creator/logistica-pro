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
    assert next(item for item in payload["items"] if item["id"] == incomplete["id"])["status"] == "incompleta"
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
