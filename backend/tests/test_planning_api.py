from fastapi.testclient import TestClient

from app.main import app
from tests.planning_helpers import (
    FIXTURE_DIR,
    save_normalized_imports,
    simple_rows,
)


client = TestClient(app)


def generated_payload(routes: int = 1, drivers: int = 2, vehicles: int = 2):
    planning, fleet = simple_rows(routes, drivers, vehicles)
    planning_id, fleet_id = save_normalized_imports(planning, fleet)
    response = client.post(
        "/api/planning/generate",
        json={
            "planning_import_id": planning_id,
            "fleet_import_id": fleet_id,
            "operation_date": "2026-07-20",
        },
    )
    assert response.status_code == 200
    return response.json()


def test_generate_endpoint():
    payload = generated_payload()
    assert payload["planning"]["id"]
    assert payload["assignments"][0]["route_id"] == "R001"


def test_latest_endpoint():
    generated = generated_payload()
    response = client.get("/api/planning/latest")
    assert response.status_code == 200
    assert response.json()["planning"]["id"] == generated["planning"]["id"]


def test_get_planning_endpoint():
    generated = generated_payload()
    planning_id = generated["planning"]["id"]
    response = client.get(f"/api/planning/{planning_id}")
    assert response.status_code == 200
    assert response.json()["summary"]["routes_total"] == 1


def test_patch_assignment_endpoint():
    generated = generated_payload()
    assignment_id = generated["assignments"][0]["id"]
    response = client.patch(
        f"/api/planning/assignments/{assignment_id}",
        json={"plate": "AA002AA", "confirm": True},
    )
    assert response.status_code == 200
    assert response.json()["manual_override"] is True


def test_recalculate_endpoint():
    generated = generated_payload()
    planning_id = generated["planning"]["id"]
    response = client.post(f"/api/planning/{planning_id}/recalculate", json={})
    assert response.status_code == 200
    assert response.json()["planning"]["version"] == 2


def test_simulate_event_endpoint():
    generated = generated_payload()
    planning_id = generated["planning"]["id"]
    response = client.post(
        f"/api/planning/{planning_id}/simulate-event",
        json={
            "event_type": "driver_absent",
            "entity_type": "driver",
            "entity_id": "driver01",
            "reason": "Assenza sintetica",
        },
    )
    assert response.status_code == 200
    assert response.json()["diff"]["assignment_changes"]


def test_apply_event_endpoint():
    generated = generated_payload()
    planning_id = generated["planning"]["id"]
    response = client.post(
        f"/api/planning/{planning_id}/apply-event",
        json={
            "event_type": "route_aborted",
            "entity_type": "route",
            "entity_id": "R001",
            "reason": "Abort sintetico",
        },
    )
    assert response.status_code == 200
    assert response.json()["version"] == 2


def test_history_endpoint():
    generated = generated_payload()
    planning_id = generated["planning"]["id"]
    response = client.get(f"/api/planning/{planning_id}/history")
    assert response.status_code == 200
    assert len(response.json()["versions"]) == 1


def test_export_endpoint():
    generated = generated_payload()
    planning_id = generated["planning"]["id"]
    response = client.get(f"/api/planning/{planning_id}/export?format=csv")
    assert response.status_code == 200
    assert "text/csv" in response.headers["content-type"]
    assert "route_id" in response.text


def test_generate_endpoint_without_planning():
    response = client.post(
        "/api/planning/generate",
        json={"operation_date": "2026-07-20"},
    )
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "MISSING_PLANNING_IMPORT"


def test_generate_endpoint_without_fleet():
    planning, _ = simple_rows(routes=1, drivers=1, vehicles=1)
    from app.repositories.import_repository import save_import

    save_import(
        "planning",
        "planning-only.csv",
        None,
        [],
        [item.model_dump(mode="json") for item in planning],
    )
    response = client.post(
        "/api/planning/generate",
        json={"operation_date": "2026-07-20"},
    )
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "MISSING_FLEET_IMPORT"


def test_realistic_csv_import_and_planning_generation_endpoint():
    planning_content = (FIXTURE_DIR / "realistic_planning.csv").read_bytes()
    fleet_content = (FIXTURE_DIR / "realistic_fleet.csv").read_bytes()
    planning_response = client.post(
        "/api/imports/planning",
        files={"file": ("realistic_planning.csv", planning_content, "text/csv")},
    )
    fleet_response = client.post(
        "/api/imports/fleet",
        files={"file": ("realistic_fleet.csv", fleet_content, "text/csv")},
    )
    assert planning_response.status_code == 200
    assert fleet_response.status_code == 200

    response = client.post(
        "/api/planning/generate",
        json={
            "planning_import_id": planning_response.json()["import_id"],
            "fleet_import_id": fleet_response.json()["import_id"],
            "operation_date": "2026-07-20",
            "configuration": {
                "reserve_vehicle_threshold_global": 1,
                "reserve_vehicle_threshold_by_station": {"DLO1": 1, "DLO2": 1},
            },
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["routes_total"] == 20
    assert len(payload["station_capacity"]) == 2
