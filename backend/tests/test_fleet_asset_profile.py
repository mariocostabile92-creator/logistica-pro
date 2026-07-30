from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)
ASSETS = "/api/plugins/fleet/v1/assets"


def asset():
    response = client.post(ASSETS, json={
        "external_identifier": "PROFILE-VAN-01",
        "plate": "FP123AA",
        "category": "Furgone",
        "status": "active",
        "availability": "available",
        "capabilities": [],
    })
    assert response.status_code == 201
    return response.json()


def save(asset_id: int, **changes):
    payload = {
        "contract_type": "lungo_termine",
        "company": "Mobilità Italia",
        "owner_company": "Fleet Holding",
        "contract_number": "LT-2026-001",
        "monthly_fee": "790.00",
        "daily_cost": "35.00",
        "deductible": "500.00",
        "included_km": 120000,
        "excess_km_cost": "0.12",
        "starts_on": "2026-01-01",
        "expires_on": "2029-12-31",
        "purchased_on": None,
        "contract_status": "attivo",
        **changes,
    }
    return client.put(f"{ASSETS}/{asset_id}/profile", json=payload)


def test_profile_creation_visibility_update_and_contract_rules():
    vehicle = asset()
    created = save(vehicle["id"])
    assert created.status_code == 200
    profile = created.json()
    assert profile["contract_type"] == "lungo_termine"
    assert profile["monthly_fee"] == "790.00"
    assert profile["daily_cost"] is None

    detail = client.get(f"{ASSETS}/{vehicle['id']}").json()
    assert detail["profile"]["contract_number"] == "LT-2026-001"
    listing = client.get(ASSETS).json()["items"]
    assert listing[0]["profile"]["deductible"] == "500.00"

    short_term = save(
        vehicle["id"],
        contract_type="breve_termine",
        daily_cost="42.50",
    )
    assert short_term.status_code == 200
    assert short_term.json()["monthly_fee"] is None
    assert short_term.json()["daily_cost"] == "42.50"

    owned = save(
        vehicle["id"],
        contract_type="proprieta",
        owner_company="Operations Srl",
        purchased_on="2025-05-10",
    ).json()
    assert owned["monthly_fee"] is None
    assert owned["daily_cost"] is None
    assert owned["purchased_on"] == "2025-05-10"


def test_profile_contract_specific_validation():
    vehicle = asset()
    missing_company = save(
        vehicle["id"],
        contract_type="leasing",
        company="",
    )
    assert missing_company.status_code == 422
    missing_monthly = save(
        vehicle["id"],
        contract_type="lungo_termine",
        monthly_fee=None,
    )
    assert missing_monthly.status_code == 422
    missing_daily = save(
        vehicle["id"],
        contract_type="breve_termine",
        daily_cost=None,
    )
    assert missing_daily.status_code == 422
    invalid_dates = save(
        vehicle["id"],
        starts_on="2028-01-01",
        expires_on="2027-12-31",
    )
    assert invalid_dates.status_code == 422


def test_profile_is_exposed_to_damage_and_maintenance():
    vehicle = asset()
    save(vehicle["id"], contract_type="lungo_termine")
    damage = client.post("/api/fleet/damage-cases", json={
        "vehicle_id": vehicle["id"],
        "occurred_at": "2026-07-30T10:00:00Z",
        "origin": "manual",
        "manual_reason": "Segnalazione Fleet",
        "description": "Danno paraurti",
        "severity": "media",
        "vehicle_operational_status": "disponibile",
    })
    assert damage.status_code == 201
    assert damage.json()["asset_profile"]["contract_type"] == "lungo_termine"

    maintenance = client.post("/api/fleet/maintenances", json={
        "vehicle_id": vehicle["id"],
        "description": "Controllo paraurti",
        "maintenance_type": "carrozzeria",
    })
    assert maintenance.status_code == 201
    context = maintenance.json()["asset_profile"]
    assert context["company"] == "Mobilità Italia"
    assert context["contract_number"] == "LT-2026-001"
    assert context["deductible"] == "500.00"
