from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)
BASE_URL = "/api/configuration/v1"


def section(key, **values):
    return {
        "key": key,
        "values": [
            {"key": value_key, "value": value}
            for value_key, value in values.items()
        ],
    }


def test_current_returns_safe_platform_defaults():
    response = client.get(f"{BASE_URL}/current")

    assert response.status_code == 200
    payload = response.json()
    assert payload["version"]["number"] == 0
    assert payload["metadata"]["contract_version"] == "1.0"
    assert payload["metadata"]["fallback_used"] is True
    assert len(payload["sections"]) == 8


def test_validate_does_not_persist_invalid_configuration():
    response = client.post(
        f"{BASE_URL}/validate",
        json={
            "organization_id": "org-api",
            "sections": [
                section("reserve_policy", default_threshold=-1)
            ],
        },
    )

    assert response.status_code == 200
    assert response.json()["valid"] is False
    assert client.get(
        f"{BASE_URL}/versions?organization_id=org-api"
    ).json()["items"] == []


def test_create_current_and_list_organization_version():
    created = client.post(
        f"{BASE_URL}/versions",
        json={
            "organization_id": "org-api",
            "created_by": "integration_test",
            "note": "Organization vocabulary",
            "sections": [
                section("nomenclature", asset_label="Equipment")
            ],
        },
    )

    assert created.status_code == 201
    assert created.json()["version"]["number"] == 1
    assert (
        created.json()["metadata"]["resolved_scope"]["organization_id"]
        == "org-api"
    )

    current = client.get(
        f"{BASE_URL}/current?organization_id=org-api"
    )
    nomenclature = next(
        item
        for item in current.json()["sections"]
        if item["key"] == "nomenclature"
    )
    asset_label = next(
        item
        for item in nomenclature["values"]
        if item["key"] == "asset_label"
    )
    assert asset_label == {
        "key": "asset_label",
        "value": "Equipment",
        "source": "organization",
    }

    versions = client.get(
        f"{BASE_URL}/versions?organization_id=org-api"
    )
    assert [item["number"] for item in versions.json()["items"]] == [1]


def test_create_rejects_invalid_configuration():
    response = client.post(
        f"{BASE_URL}/versions",
        json={
            "organization_id": "org-invalid",
            "sections": [
                section(
                    "generic_mappings",
                    auto_mapping_min_confidence=2,
                )
            ],
        },
    )

    assert response.status_code == 422
    assert client.get(
        f"{BASE_URL}/versions?organization_id=org-invalid"
    ).json()["items"] == []


def test_operational_unit_falls_back_to_organization():
    client.post(
        f"{BASE_URL}/versions",
        json={
            "organization_id": "org-fallback",
            "sections": [
                section("nomenclature", task_label="Work Item")
            ],
        },
    )

    response = client.get(
        f"{BASE_URL}/current"
        "?organization_id=org-fallback"
        "&operational_unit_id=unit-one"
    )

    assert response.status_code == 200
    metadata = response.json()["metadata"]
    assert metadata["requested_scope"]["operational_unit_id"] == "unit-one"
    assert metadata["resolved_scope"]["operational_unit_id"] is None
    assert metadata["fallback_used"] is True
