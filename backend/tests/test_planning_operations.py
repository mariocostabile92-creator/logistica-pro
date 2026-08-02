from fastapi.testclient import TestClient

from app.main import app
from app.auth.domain import Role
from app.auth.password_service import hash_password
from app.auth.repository import create_user
from tests.planning_helpers import save_normalized_imports, simple_rows


client = TestClient(app)


def _generated(routes=2, drivers=2, vehicles=2):
    planning_rows, fleet_rows = simple_rows(routes, drivers, vehicles)
    planning_import_id, fleet_import_id = save_normalized_imports(
        planning_rows, fleet_rows
    )
    response = client.post(
        "/api/planning/generate",
        json={
            "planning_import_id": planning_import_id,
            "fleet_import_id": fleet_import_id,
            "operation_date": "2026-08-03",
            "station": "DLO1",
        },
    )
    assert response.status_code == 200
    return response.json()


def test_operational_snapshot_uses_real_assignments_and_convocations():
    generated = _generated()
    response = client.get("/api/planning/operations")
    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["routes_definitive"] == 2
    assert payload["summary"]["routes_complete"] == 2
    assert len(payload["convocations"]) == 2
    assert payload["routes"][0]["convocation"]["status"] == "da_preparare"
    assert payload["planning"]["id"] == generated["planning"]["id"]
    assert payload["workforce"]["operation_date"] == "2026-08-03"
    assert "callable" in payload["workforce"]["summary"]


def test_forecast_remains_distinct_from_definitive_routes():
    _generated()
    response = client.post(
        "/api/planning/operations/forecast",
        json={
            "station": "DLO1",
            "source_filename": "amazon-forecast.xlsx",
            "days": [
                {"operation_date": f"2026-08-{day:02d}", "routes_expected": 70 + day}
                for day in range(3, 10)
            ],
        },
    )
    assert response.status_code == 200
    payload = client.get("/api/planning/operations").json()
    assert len(payload["forecast"]["days"]) == 7
    assert payload["summary"]["routes_forecast"] == 73
    assert payload["summary"]["routes_definitive"] == 2


def test_convocation_update_is_persisted_and_audited():
    generated = _generated()
    assignment_id = generated["assignments"][0]["id"]
    planning_id = generated["planning"]["id"]
    response = client.patch(
        f"/api/planning/operations/{planning_id}/convocations/{assignment_id}",
        json={"status": "pronta", "scheduled_time": "08:15"},
    )
    assert response.status_code == 200
    assert response.json()["scheduled_time"] == "08:15"
    payload = client.get("/api/planning/operations").json()
    assert payload["summary"]["convocations_ready"] == 1
    assert payload["audit"][0]["change_type"] == "convocation_updated"


def test_operational_lifecycle_confirms_then_publishes():
    generated = _generated()
    planning_id = generated["planning"]["id"]
    confirmed = client.post(
        f"/api/planning/operations/{planning_id}/confirm", json={}
    )
    assert confirmed.status_code == 200
    assert confirmed.json()["status"] == "confirmed"
    published = client.post(
        f"/api/planning/operations/{planning_id}/publish", json={}
    )
    assert published.status_code == 200
    assert published.json()["status"] == "published"
    snapshot = client.get("/api/planning/operations").json()
    assert snapshot["lifecycle"]["state"] == "published"


def test_incomplete_plan_cannot_be_confirmed():
    generated = _generated(routes=3, drivers=2, vehicles=2)
    planning_id = generated["planning"]["id"]
    response = client.post(
        f"/api/planning/operations/{planning_id}/confirm", json={}
    )
    assert response.status_code == 422


def test_isolated_qa_day_exposes_78_routes_and_73_complete():
    generated = _generated(routes=78, drivers=75, vehicles=76)
    complete = [item for item in generated["assignments"] if item["driver_id"] and item["plate"]]
    missing = [item for item in generated["assignments"] if not item["driver_id"]]
    released = [complete[0]["plate"], complete[1]["plate"]]
    for assignment in complete[:2]:
        assert client.patch(
            f"/api/planning/assignments/{assignment['id']}",
            json={"remove_vehicle": True},
        ).status_code == 200
    for assignment, plate in zip(missing, [*released, "AA076AA"], strict=True):
        assert client.patch(
            f"/api/planning/assignments/{assignment['id']}",
            json={"plate": plate},
        ).status_code == 200
    payload = client.get("/api/planning/operations").json()
    assert payload["summary"]["routes_definitive"] == 78
    assert payload["summary"]["drivers_assigned"] == 75
    assert payload["summary"]["vehicles_assigned"] == 76
    assert payload["summary"]["routes_complete"] == 73
    assert payload["summary"]["routes_incomplete"] == 5


def _role_client(role: Role):
    password = "PlanningRole!2026"
    email = f"{role.value}@example.test"
    create_user(email, hash_password(password), role, f"QA {role.value}")
    role_client = TestClient(app, headers={"X-Auth-Enforce": "1"})
    response = role_client.post(
        "/api/auth/login",
        json={"email": email, "password": password, "remember_me": False},
    )
    assert response.status_code == 200
    return role_client


def test_viewer_reads_planning_but_cannot_mutate_it():
    _generated()
    viewer = _role_client(Role.VIEWER)
    snapshot = viewer.get("/api/planning/operations")
    assert snapshot.status_code == 200
    assert snapshot.json()["permissions"]["write"] is False
    mutation = viewer.post(
        "/api/planning/operations/forecast",
        json={
            "station": "DLO1",
            "source_filename": "forbidden.xlsx",
            "days": [{"operation_date": "2026-08-03", "routes_expected": 2}],
        },
    )
    assert mutation.status_code == 403


def test_dispatcher_can_manage_operational_planning():
    _generated()
    dispatcher = _role_client(Role.DISPATCHER)
    snapshot = dispatcher.get("/api/planning/operations")
    assert snapshot.status_code == 200
    assert snapshot.json()["permissions"]["write"] is True
    mutation = dispatcher.post(
        "/api/planning/operations/forecast",
        json={
            "station": "DLO1",
            "source_filename": "dispatcher.xlsx",
            "days": [{"operation_date": "2026-08-03", "routes_expected": 2}],
        },
    )
    assert mutation.status_code == 200
