from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app
from app.plugins.fleet.rentals.infrastructure import repository


client = TestClient(app)
ASSETS = "/api/plugins/fleet/v1/assets"
DAMAGE = "/api/fleet/damage-cases"
MAINTENANCE = "/api/fleet/maintenances"
RENTALS = "/api/fleet/rentals"


def asset():
    response = client.post(ASSETS, json={
        "external_identifier": "RENT-VAN-01", "plate": "RN001AA",
        "category": "Furgone", "status": "active",
        "availability": "available", "capabilities": [],
    })
    assert response.status_code == 201
    return response.json()


def payload(**changes):
    return {
        "replacement_vehicle": "Ford Transit RN-REPL",
        "rental_company": "Mobility Rent",
        "contract_number": "RENT-2026-01",
        "start_date": "2026-08-01",
        "expected_end_date": "2026-08-15",
        "end_date": None,
        "reason": "altro",
        "status": "programmato",
        "notes": "Copertura operativa",
        **changes,
    }


def test_create_update_list_detail_and_operational_need():
    vehicle = asset()
    created = client.post(RENTALS, json=payload(vehicle_id=vehicle["id"]))
    assert created.status_code == 201
    item = created.json()
    assert item["plate"] == "RN001AA"
    assert client.get(f"{RENTALS}/{item['id']}").status_code == 200
    listing = client.get(RENTALS, params={"vehicle_id": vehicle["id"]}).json()
    assert listing["summary"]["scheduled"] == 1

    updated = client.patch(f"{RENTALS}/{item['id']}", json={
        "status": "attivo", "expected_end_date": "2026-08-20",
    })
    assert updated.status_code == 200
    assert updated.json()["status"] == "attivo"
    assert client.get(RENTALS).json()["summary"]["replaced_vehicles"] == 1

    operational = client.post(RENTALS, json=payload(
        contract_number=None, reason="picco_operativo",
        replacement_vehicle="Fiat Ducato Extra",
    ))
    assert operational.status_code == 201
    assert operational.json()["vehicle_id"] is None


def test_damage_and_maintenance_create_linked_rentals():
    vehicle = asset()
    damage = client.post(DAMAGE, json={
        "vehicle_id": vehicle["id"], "occurred_at": "2026-07-30T09:00:00Z",
        "origin": "manual", "manual_reason": "Segnalazione Fleet",
        "description": "Urto", "severity": "alta",
        "vehicle_operational_status": "indisponibile",
    }).json()
    from_damage = client.post(RENTALS, json=payload(
        damage_case_id=damage["id"], reason="danno",
    ))
    assert from_damage.status_code == 201
    assert from_damage.json()["vehicle_id"] == vehicle["id"]
    assert from_damage.json()["damage_case_number"] == damage["case_number"]

    maintenance = client.post(MAINTENANCE, json={
        "vehicle_id": vehicle["id"], "description": "Tagliando",
        "maintenance_type": "tagliando", "status": "programmata",
        "priority": "media",
    }).json()
    from_maintenance = client.post(RENTALS, json=payload(
        maintenance_id=maintenance["id"], reason="manutenzione",
        replacement_vehicle="Opel Movano sostitutivo",
    ))
    assert from_maintenance.status_code == 201
    assert from_maintenance.json()["vehicle_id"] == vehicle["id"]
    assert from_maintenance.json()["maintenance_number"] == maintenance["maintenance_number"]


def test_validation_and_idempotent_schema():
    assert client.post(RENTALS, json=payload(reason="fattura")).status_code == 422
    assert client.post(RENTALS, json=payload(
        start_date="2026-08-20", expected_end_date="2026-08-01",
    )).status_code == 422
    assert client.post(RENTALS, json=payload(maintenance_id=999999)).status_code == 404
    repository.init_schema()
    repository.init_schema()
    assert "PRAGMA" not in Path(repository.__file__).read_text(encoding="utf-8")
