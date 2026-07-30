from fastapi.testclient import TestClient

from app.core.database import db_session
from app.main import app

client = TestClient(app)
ASSETS = "/api/plugins/fleet/v1/assets"
VISION = "/api/fleet/vision"


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
        "status": "attiva",
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
    }
    insight = payload["items"][0]
    assert insight["contract_type"] == "lungo_termine"
    assert insight["damage_open"] == 1
    assert insight["maintenance_open"] == 1
    assert insight["missing_documents"] == 1
    assert insight["insurance"]["policy_number"] == "FVE-POL-1"
    assert insight["franchises_open"] == 1
    assert insight["rentals_active"] == 1
    assert insight["deadlines_imminent"] >= 1
    assert "risk_score" not in insight
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
