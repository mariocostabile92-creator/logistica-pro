from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app
from app.plugins.fleet.insurance.infrastructure import repository


client = TestClient(app)
ASSETS = "/api/plugins/fleet/v1/assets"
DAMAGE = "/api/fleet/damage-cases"
FRANCHISES = "/api/fleet/franchises"
POLICIES = "/api/fleet/insurance-policies"


def asset(identifier: str = "INS-VAN-01"):
    response = client.post(ASSETS, json={
        "external_identifier": identifier,
        "plate": "IN001AA",
        "category": "Furgone",
        "status": "active",
        "availability": "available",
        "capabilities": [],
    })
    assert response.status_code == 201
    return response.json()


def policy(vehicle_id: int, **changes):
    return {
        "vehicle_id": vehicle_id,
        "company": "Protezione Fleet",
        "policy_number": f"POL-{vehicle_id}-2026",
        "coverage_type": "kasko",
        "starts_on": "2026-01-01",
        "expires_on": "2026-12-31",
        "coverage_limit": "1000000.00",
        "insurance_deductible": "350.00",
        "notes": "Copertura completa",
        "status": "attiva",
        **changes,
    }


def damage(vehicle_id: int):
    response = client.post(DAMAGE, json={
        "vehicle_id": vehicle_id,
        "occurred_at": "2026-07-30T09:00:00Z",
        "origin": "manual",
        "manual_reason": "Segnalazione Fleet",
        "description": "Urto laterale",
        "severity": "alta",
        "vehicle_operational_status": "indisponibile",
    })
    assert response.status_code == 201
    return response.json()


def test_policy_creation_list_detail_update_and_unique_vehicle_link():
    vehicle = asset()
    created = client.post(POLICIES, json=policy(vehicle["id"]))
    assert created.status_code == 201
    item = created.json()
    assert item["plate"] == "IN001AA"
    assert item["coverage_limit"] == "1000000.00"
    assert item["insurance_deductible"] == "350.00"

    listing = client.get(POLICIES, params={"vehicle_id": vehicle["id"]}).json()
    assert listing["summary"]["active"] == 1
    assert listing["items"][0]["id"] == item["id"]
    assert client.get(f"{POLICIES}/{item['id']}").status_code == 200

    updated = client.patch(f"{POLICIES}/{item['id']}", json={
        "status": "in_scadenza",
        "expires_on": "2026-09-30",
        "insurance_deductible": "500.00",
    })
    assert updated.status_code == 200
    assert updated.json()["status"] == "in_scadenza"
    assert updated.json()["insurance_deductible"] == "500.00"

    duplicate = client.post(POLICIES, json=policy(
        vehicle["id"], policy_number="POL-DUPLICATE",
    ))
    assert duplicate.status_code == 409


def test_damage_and_franchise_read_one_live_policy_without_copying_data():
    vehicle = asset("INS-VAN-02")
    created_policy = client.post(POLICIES, json=policy(vehicle["id"])).json()
    damage_case = damage(vehicle["id"])
    damage_detail = client.get(f"{DAMAGE}/{damage_case['id']}").json()
    assert damage_detail["insurance_policy"]["id"] == created_policy["id"]
    assert damage_detail["insurance_policy"]["company"] == "Protezione Fleet"

    franchise = client.post(FRANCHISES, json={
        "damage_case_id": damage_case["id"],
    }).json()
    assert franchise["insurance_policy_id"] == created_policy["id"]
    assert franchise["insurance_policy_number"] == created_policy["policy_number"]

    client.patch(f"{POLICIES}/{created_policy['id']}", json={
        "company": "Nuova Compagnia",
    })
    refreshed_damage = client.get(f"{DAMAGE}/{damage_case['id']}").json()
    refreshed_franchise = client.get(f"{FRANCHISES}/{franchise['id']}").json()
    assert refreshed_damage["insurance_policy"]["company"] == "Nuova Compagnia"
    assert refreshed_franchise["insurance_company"] == "Nuova Compagnia"


def test_validation_missing_vehicle_and_idempotent_schema():
    vehicle = asset("INS-VAN-03")
    assert client.post(
        POLICIES, json=policy(vehicle["id"], coverage_type="sinistri"),
    ).status_code == 422
    assert client.post(
        POLICIES, json=policy(vehicle["id"], status="ignota"),
    ).status_code == 422
    assert client.post(POLICIES, json=policy(999999)).status_code == 404
    repository.init_schema()
    repository.init_schema()
    assert "PRAGMA" not in Path(repository.__file__).read_text(encoding="utf-8")
