import base64

from fastapi.testclient import TestClient

from app.main import app
from tests.journal_evidence_helpers import upload_required_evidence


client = TestClient(app)
BASE = "/api/plugins/fleet/v1"
JOURNAL = f"{BASE}/journal"
PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk"
    "YAAAAAYAAjCB0C8AAAAASUVORK5CYII="
)


def create_asset():
    response = client.post(
        f"{BASE}/assets",
        json={
            "external_identifier": "vehicle-library-001",
            "plate": "VL001AA",
            "category": "Furgone elettrico",
            "status": "active",
            "availability": "available",
            "capabilities": ["electric", "lt"],
        },
    )
    assert response.status_code == 201
    return response.json()


def create_movement(asset, operation, submission, odometer):
    opened = client.post(
        f"{JOURNAL}/sessions",
        json={
            "operation_type": operation,
            "plate": asset["plate"],
            "declared_driver_identifier": "DRV-LIB-01",
            "operational_shift": "morning" if operation == "check_out" else None,
        },
    ).json()
    uploaded = client.post(
        f"{JOURNAL}/sessions/{opened['id']}/media",
        headers={"X-Journal-Token": opened["token"]},
        files={"file": ("mezzo.png", PNG + submission.encode(), "image/png")},
    )
    assert uploaded.status_code == 201
    payload = {
        "odometer_km": odometer,
        "fuel_percentage": 72,
        "cleanliness_status": "compliant" if operation == "check_in" else None,
        "anomaly_present": operation == "check_in",
        "anomaly_description": "Graffio laterale" if operation == "check_in" else None,
        "equipment": [
            {"code": "telepass", "status": "present"},
            {"code": "phone", "status": "present"},
            {"code": "keys", "status": "present"},
            {"code": "fuel_card", "status": "present"},
        ],
        "client_submission_id": submission,
        "timezone": "Europe/Rome",
    }
    upload_required_evidence(client, JOURNAL, opened, submission)
    completed = client.post(
        f"{JOURNAL}/sessions/{opened['id']}/complete",
        headers={"X-Journal-Token": opened["token"]},
        json=payload,
    )
    assert completed.status_code == 200
    return completed.json(), uploaded.json()


def test_vehicle_history_reads_journal_without_copying_movements():
    asset = create_asset()
    first, _ = create_movement(asset, "check_out", "vl-out-001", 42000)
    second, media = create_movement(asset, "check_in", "vl-in-001", 42148)

    response = client.get(
        f"{JOURNAL}/vehicles/{asset['id']}/history"
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["asset"]["plate"] == "VL001AA"
    assert payload["asset"]["model"] == "Furgone elettrico"
    assert payload["asset"]["term"] == "LT"
    assert payload["kpis"]["current_odometer_km"] == 42148
    assert payload["kpis"]["last_declared_driver"] == "DRV-LIB-01"
    assert payload["kpis"]["last_movement"] == "check_in"
    assert [item["id"] for item in payload["movements"]] == [
        second["id"],
        first["id"],
    ]
    detail = payload["movements"][0]
    assert detail["anomaly_description"] == "Graffio laterale"
    assert len(detail["equipment"]) == 4
    assert detail["media"][0]["id"] == media["id"]
    assert detail["media"][0]["url"].endswith(media["id"])


def test_vehicle_library_is_read_only_and_serves_existing_photos():
    asset = create_asset()
    _, media = create_movement(asset, "check_out", "vl-photo-001", 100)

    photo = client.get(f"/api/fleet/journal-control-room/media/{media['id']}")

    assert photo.status_code == 200
    assert photo.headers["content-type"] == "image/png"
    assert photo.content == PNG + b"vl-photo-001"
    assert client.post(
        f"{JOURNAL}/vehicles/{asset['id']}/history"
    ).status_code == 405


def test_missing_vehicle_history_returns_not_found():
    response = client.get(f"{JOURNAL}/vehicles/999999/history")
    assert response.status_code == 404


def test_vehicle_library_frontend_contract():
    response = client.get("/app/vehicles/")
    assert response.status_code == 200
    html = response.text
    assert "Vehicle Library" in html
    assert "Cartella operativa" in html
    assert 'aria-current="page">Fleet' in html
    assert "Documenti operativi" in html
    assert "Cerca data, driver o tipo movimentazione" in html
    assert "Giorni fermo" in html
    assert "BT/LT" in html
