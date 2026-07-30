from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app
from app.plugins.fleet.franchises.infrastructure import repository


client = TestClient(app)
ASSETS = "/api/plugins/fleet/v1/assets"
DAMAGE = "/api/fleet/damage-cases"
MAINTENANCE = "/api/fleet/maintenances"
FRANCHISES = "/api/fleet/franchises"


def asset():
    response = client.post(ASSETS, json={
        "external_identifier": "FR-VAN-01",
        "plate": "FR001AA",
        "category": "Furgone",
        "status": "active",
        "availability": "available",
        "capabilities": [],
    })
    assert response.status_code == 201
    vehicle = response.json()
    profile = client.put(f"{ASSETS}/{vehicle['id']}/profile", json={
        "contract_type": "lungo_termine",
        "company": "Mobilità Contratti",
        "contract_number": "LT-FR-001",
        "monthly_fee": "700.00",
        "deductible": "650.00",
        "included_km": 100000,
        "starts_on": "2026-01-01",
        "expires_on": "2029-12-31",
        "contract_status": "attivo",
    })
    assert profile.status_code == 200
    return vehicle


def damage(vehicle_id: int):
    response = client.post(DAMAGE, json={
        "vehicle_id": vehicle_id,
        "occurred_at": "2026-07-30T09:00:00Z",
        "origin": "manual",
        "manual_reason": "Segnalazione Fleet",
        "description": "Danno laterale",
        "severity": "alta",
        "vehicle_operational_status": "indisponibile",
    })
    assert response.status_code == 201
    return response.json()


def test_franchise_workflow_reads_live_asset_profile_without_duplication():
    vehicle = asset()
    damage_case = damage(vehicle["id"])
    created = client.post(FRANCHISES, json={
        "damage_case_id": damage_case["id"],
        "motivation": "Verifica condizioni contrattuali",
    })
    assert created.status_code == 201
    item = created.json()
    assert item["status"] == "da_valutare"
    assert item["franchise_expected"] == "650.00"
    assert item["contract_number"] == "LT-FR-001"
    assert item["contract_company"] == "Mobilità Contratti"
    assert "deductible" not in item

    duplicate = client.post(FRANCHISES, json={
        "damage_case_id": damage_case["id"],
    })
    assert duplicate.status_code == 201
    assert duplicate.json()["id"] == item["id"]

    changed = client.put(f"{ASSETS}/{vehicle['id']}/profile", json={
        "contract_type": "lungo_termine",
        "company": "Mobilità Contratti",
        "contract_number": "LT-FR-001",
        "monthly_fee": "700.00",
        "deductible": "800.00",
        "included_km": 100000,
        "starts_on": "2026-01-01",
        "expires_on": "2029-12-31",
        "contract_status": "attivo",
    })
    assert changed.status_code == 200
    assert client.get(f"{FRANCHISES}/{item['id']}").json()["franchise_expected"] == "800.00"


def test_franchise_list_detail_status_and_late_maintenance_link():
    vehicle = asset()
    damage_case = damage(vehicle["id"])
    item = client.post(FRANCHISES, json={
        "damage_case_id": damage_case["id"],
    }).json()
    maintenance = client.post(MAINTENANCE, json={
        "damage_case_id": damage_case["id"],
        "description": "Sostituzione pannello",
        "maintenance_type": "carrozzeria",
        "priority": "alta",
        "status": "programmata",
    })
    assert maintenance.status_code == 201

    listing = client.get(FRANCHISES, params={"vehicle_id": vehicle["id"]}).json()
    assert listing["summary"]["to_evaluate"] == 1
    assert listing["items"][0]["maintenance_number"] == maintenance.json()["maintenance_number"]

    updated = client.patch(f"{FRANCHISES}/{item['id']}", json={
        "status": "in_verifica",
        "motivation": "Preventivo in analisi",
        "notes": "Confronto con società",
    })
    assert updated.status_code == 200
    assert updated.json()["status"] == "in_verifica"
    assert updated.json()["motivation"] == "Preventivo in analisi"
    assert client.patch(
        f"{FRANCHISES}/{item['id']}", json={"status": "ignota"},
    ).status_code == 422


def test_missing_damage_and_idempotent_cross_database_schema():
    assert client.post(FRANCHISES, json={"damage_case_id": 999999}).status_code == 404
    repository.init_schema()
    repository.init_schema()
    source = Path(repository.__file__).read_text(encoding="utf-8")
    assert "PRAGMA" not in source
