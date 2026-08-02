from datetime import date, timedelta

from fastapi.testclient import TestClient

from app.core.database import db_session
from app.main import app

client = TestClient(app)
ASSETS = "/api/plugins/fleet/v1/assets"
DEADLINES = "/api/fleet/deadlines"


def test_aggregates_five_sources_without_deadline_table():
    vehicle = client.post(ASSETS, json={
        "external_identifier": "SCAD-01", "plate": "SC001AA",
        "category": "Furgone", "status": "active",
        "availability": "available", "capabilities": [],
    }).json()
    today = date.today()
    dates = [(today - timedelta(days=1)).isoformat(), today.isoformat(),
             (today + timedelta(days=5)).isoformat(), (today + timedelta(days=20)).isoformat()]
    assert client.post("/api/fleet/documents", json={
        "vehicle_id": vehicle["id"], "document_type": "revisione",
        "title": "Revisione", "expires_at": dates[0], "status": "scaduto",
    }).status_code == 201
    assert client.post("/api/fleet/insurance-policies", json={
        "vehicle_id": vehicle["id"], "company": "Sicura", "policy_number": "SCAD-POL-1",
        "coverage_type": "rca", "starts_on": "2026-01-01",
        "expires_on": dates[1], "status": "attiva",
    }).status_code == 201
    assert client.put(f"{ASSETS}/{vehicle['id']}/profile", json={
        "contract_type": "lungo_termine", "company": "Mobility",
        "contract_number": "SCAD-LT-1", "monthly_fee": "500",
        "deductible": "300", "included_km": 90000,
        "starts_on": "2026-01-01", "expires_on": dates[2],
        "contract_status": "attivo",
    }).status_code == 200
    assert client.post("/api/fleet/maintenances", json={
        "vehicle_id": vehicle["id"], "description": "Tagliando programmato",
        "maintenance_type": "tagliando", "status": "programmata",
        "priority": "media", "expected_at": dates[3],
    }).status_code == 201
    assert client.post("/api/fleet/rentals", json={
        "vehicle_id": vehicle["id"], "replacement_vehicle": "SCAD-RENT-1",
        "rental_company": "Rent Fleet", "start_date": today.isoformat(),
        "expected_end_date": (today + timedelta(days=6)).isoformat(),
        "reason": "manutenzione", "status": "attivo",
    }).status_code == 201

    response = client.get(DEADLINES, params={"vehicle_id": vehicle["id"]})
    assert response.status_code == 200
    payload = response.json()
    assert {item["source_module"] for item in payload["items"]} == {
        "document", "insurance", "contract", "maintenance",
        "rental",
    }
    assert payload["summary"] == {
        "expired": 1, "expiring": 4, "today": 1, "next_30_days": 4,
    }
    assert {item["status"] for item in payload["items"]} == {
        "Scaduta", "Oggi", "Prossimi 7 giorni", "Prossimi 30 giorni",
    }
    with db_session() as conn:
        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE '%deadline%'"
        ).fetchall()
    assert tables == []


def test_filters_vehicle_and_ignores_completed_maintenance():
    first = client.post(ASSETS, json={
        "external_identifier": "SCAD-02", "plate": "SC002AA",
        "category": "Van", "status": "active", "availability": "available", "capabilities": [],
    }).json()
    second = client.post(ASSETS, json={
        "external_identifier": "SCAD-03", "plate": "SC003AA",
        "category": "Van", "status": "active", "availability": "available", "capabilities": [],
    }).json()
    for vehicle in (first, second):
        client.post("/api/fleet/documents", json={
            "vehicle_id": vehicle["id"], "document_type": "bollo",
            "title": "Bollo", "expires_at": "2027-01-01", "status": "valido",
        })
    items = client.get(DEADLINES, params={"vehicle_id": first["id"]}).json()["items"]
    assert len(items) == 1
    assert items[0]["plate"] == "SC002AA"
