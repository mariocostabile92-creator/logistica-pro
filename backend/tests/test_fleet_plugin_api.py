from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)
BASE_URL = "/api/plugins/fleet/v1"


def create_asset(
    external_identifier: str = "asset-001",
    plate: str | None = "ab123cd",
):
    return client.post(
        f"{BASE_URL}/assets",
        json={
            "external_identifier": external_identifier,
            "plate": plate,
            "category": "light_van",
            "status": "active",
            "availability": "available",
            "notes": "Synthetic test asset",
            "capabilities": ["electric", "large_capacity"],
        },
    )


def test_asset_registry_create_list_and_detail():
    created = create_asset()

    assert created.status_code == 201
    asset = created.json()
    assert asset["external_identifier"] == "asset-001"
    assert asset["plate"] == "AB123CD"
    assert asset["capabilities"] == ["electric", "large_capacity"]
    assert asset["documents"] == []

    listing = client.get(f"{BASE_URL}/assets")
    assert listing.status_code == 200
    assert listing.json()["contract_version"] == "1.0"
    assert [item["id"] for item in listing.json()["items"]] == [asset["id"]]

    detail = client.get(f"{BASE_URL}/assets/{asset['id']}")
    assert detail.status_code == 200
    assert detail.json() == asset


def test_asset_update_preserves_external_identifier_and_records_event():
    asset = create_asset().json()

    updated = client.patch(
        f"{BASE_URL}/assets/{asset['id']}",
        json={
            "category": "cargo_bike",
            "status": "inactive",
            "capabilities": ["urban_access"],
            "notes": None,
        },
    )

    assert updated.status_code == 200
    payload = updated.json()
    assert payload["external_identifier"] == "asset-001"
    assert payload["category"] == "cargo_bike"
    assert payload["status"] == "inactive"
    assert payload["capabilities"] == ["urban_access"]

    events = client.get(f"{BASE_URL}/assets/{asset['id']}/events").json()
    assert [item["event_type"] for item in events["items"]] == [
        "AssetCreated",
        "AssetUpdated",
    ]
    assert events["items"][1]["details"]["changes"]["category"] == {
        "before": "light_van",
        "after": "cargo_bike",
    }


def test_availability_observations_append_chronological_events():
    asset = create_asset().json()
    asset_id = asset["id"]

    observations = [
        ("unavailable", "AssetUnavailable"),
        ("maintenance", "AssetMaintenanceStarted"),
        ("reserve", "AssetMaintenanceEnded"),
        ("reserve", "AssetAvailabilityObserved"),
        ("inspection_hold", "AssetAvailabilityChanged"),
    ]
    for availability, _ in observations:
        response = client.post(
            f"{BASE_URL}/assets/{asset_id}/availability",
            json={
                "availability": availability,
                "note": f"Observed {availability}",
            },
        )
        assert response.status_code == 200
        assert response.json()["availability"] == availability

    response = client.get(f"{BASE_URL}/assets/{asset_id}/events")
    assert response.status_code == 200
    events = response.json()["items"]
    assert [event["event_type"] for event in events] == [
        "AssetCreated",
        *[event_type for _, event_type in observations],
    ]
    assert [event["id"] for event in events] == sorted(
        event["id"] for event in events
    )
    assert all(event["contract_version"] == "1.0" for event in events)


def test_document_metadata_is_stored_without_notification_logic():
    asset = create_asset().json()
    asset_id = asset["id"]

    response = client.post(
        f"{BASE_URL}/assets/{asset_id}/documents",
        json={
            "document_type": "insurance",
            "name": "Policy 2026",
            "reference": "POL-SYNTH-001",
            "issued_on": "2026-01-01",
            "expires_on": "2026-12-31",
        },
    )

    assert response.status_code == 201
    assert response.json()["document_type"] == "insurance"

    detail = client.get(f"{BASE_URL}/assets/{asset_id}").json()
    assert len(detail["documents"]) == 1
    assert detail["documents"][0]["expires_on"] == "2026-12-31"

    events = client.get(f"{BASE_URL}/assets/{asset_id}/events").json()["items"]
    assert events[-1]["event_type"] == "AssetDocumentAdded"


def test_duplicate_external_identifier_or_plate_is_rejected():
    assert create_asset().status_code == 201

    duplicate_identifier = create_asset(
        external_identifier="asset-001",
        plate="EF456GH",
    )
    duplicate_plate = create_asset(
        external_identifier="asset-002",
        plate="AB123CD",
    )

    assert duplicate_identifier.status_code == 409
    assert duplicate_plate.status_code == 409


def test_missing_asset_and_empty_patch_are_rejected():
    missing = client.get(f"{BASE_URL}/assets/999999")
    assert missing.status_code == 404

    asset = create_asset().json()
    empty_patch = client.patch(
        f"{BASE_URL}/assets/{asset['id']}",
        json={},
    )
    assert empty_patch.status_code == 422


def test_planning_routes_remain_available_with_fleet_plugin_installed():
    assert client.get("/api/planning/latest").status_code == 404
    assert client.get("/api/operations/latest").status_code == 404
