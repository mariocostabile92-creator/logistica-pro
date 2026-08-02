from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)
ASSETS = "/api/plugins/fleet/v1/assets"
MAINTENANCE = "/api/fleet/maintenances"
DAMAGE = "/api/fleet"


def asset():
    response = client.post(ASSETS, json={
        "external_identifier": "MNT-VAN-01",
        "plate": "MN123TC",
        "category": "Furgone",
        "status": "active",
        "availability": "available",
        "capabilities": [],
        "notes": None,
    })
    assert response.status_code == 201
    return response.json()


def damage_case(vehicle_id: int):
    response = client.post(f"{DAMAGE}/damage-cases", json={
        "vehicle_id": vehicle_id,
        "occurred_at": "2026-07-30T10:00:00Z",
        "origin": "manual",
        "manual_reason": "Segnalazione Fleet",
        "description": "Portiera laterale danneggiata",
        "severity": "alta",
        "vehicle_operational_status": "indisponibile",
        "repair_shop": "Officina Centrale",
    })
    assert response.status_code == 201
    return response.json()


def test_maintenance_lifecycle_list_detail_and_vehicle_history():
    vehicle = asset()
    created = client.post(MAINTENANCE, json={
        "vehicle_id": vehicle["id"],
        "description": "Tagliando periodico",
        "maintenance_type": "tagliando",
        "status": "programmata",
        "priority": "media",
        "repair_shop": "Service Nord",
        "expected_at": "2026-08-05T08:00:00Z",
        "notes": "Controllo filtri",
    })
    assert created.status_code == 201
    item = created.json()
    assert item["maintenance_number"].startswith("MNT-")
    assert item["plate"] == "MN123TC"
    assert item["events"][0]["event_type"] == "manutenzione_creata"

    listing = client.get(MAINTENANCE).json()
    assert listing["summary"] == {
        "open": 1,
        "in_workshop": 0,
        "scheduled": 1,
        "completed": 0,
        "overdue": 0,
    }
    vehicle_items = client.get(
        MAINTENANCE,
        params={"vehicle_id": vehicle["id"]},
    ).json()["items"]
    assert [entry["id"] for entry in vehicle_items] == [item["id"]]

    updated = client.patch(f"{MAINTENANCE}/{item['id']}", json={
        "status": "in_lavorazione",
        "priority": "alta",
        "notes": "Mezzo consegnato in officina",
    })
    assert updated.status_code == 200
    detail = updated.json()
    assert detail["status"] == "in_lavorazione"
    assert detail["events"][-1]["event_type"] == "stato_modificato"
    assert client.get(MAINTENANCE).json()["summary"]["in_workshop"] == 1


def test_damage_case_generates_one_linked_maintenance():
    vehicle = asset()
    damage = damage_case(vehicle["id"])
    response = client.post(MAINTENANCE, json={
        "damage_case_id": damage["id"],
        "description": "Questo testo viene sostituito dalla pratica",
        "maintenance_type": "carrozzeria",
        "priority": "alta",
        "status": "programmata",
        "repair_shop": None,
        "notes": f"Generata dalla pratica {damage['case_number']}",
    })
    assert response.status_code == 201
    maintenance = response.json()
    assert maintenance["vehicle_id"] == vehicle["id"]
    assert maintenance["plate"] == vehicle["plate"]
    assert maintenance["damage_case_id"] == damage["id"]
    assert maintenance["damage_case_number"] == damage["case_number"]
    assert maintenance["description"] == damage["description"]
    assert maintenance["repair_shop"] == "Officina Centrale"

    duplicate = client.post(MAINTENANCE, json={
        "damage_case_id": damage["id"],
        "description": damage["description"],
        "maintenance_type": "carrozzeria",
    })
    assert duplicate.status_code == 409
