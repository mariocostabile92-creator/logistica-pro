import io

from fastapi.testclient import TestClient
from openpyxl import Workbook

from app.main import app


client = TestClient(app)


def make_workbook(headers, rows):
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(headers)
    for row in rows:
        sheet.append(row)
    stream = io.BytesIO()
    workbook.save(stream)
    stream.seek(0)
    return stream


def test_health_endpoint():
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_invalid_file():
    response = client.post(
        "/api/imports/preview",
        data={"dataset_type": "planning"},
        files={"file": ("bad.txt", b"not valid", "text/plain")},
    )
    assert response.status_code == 400


def test_preview_endpoint_with_workbook():
    stream = make_workbook(["Driver", "Targa", "Route"], [["Mario Rossi", "AB123CD", "R1"]])
    response = client.post(
        "/api/imports/preview",
        data={"dataset_type": "planning"},
        files={"file": ("planning.xlsx", stream.getvalue(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["columns"] == ["Driver", "Targa", "Route"]
    assert payload["recognized_columns"]


def test_operations_dashboard_endpoints():
    planning = make_workbook(
        ["Driver", "Targa", "Route"],
        [["Driver Uno", "AB123CD", "R1"]],
    )
    fleet = make_workbook(
        ["Targa", "Autista", "Stato"],
        [
            ["AB123CD", "Driver Uno", "Operativo"],
            ["EF456GH", "Driver Due", "Operativo"],
        ],
    )

    planning_response = client.post(
        "/api/imports/planning",
        files={
            "file": (
                "planning.xlsx",
                planning.getvalue(),
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
    )
    fleet_response = client.post(
        "/api/imports/fleet",
        files={
            "file": (
                "fleet.xlsx",
                fleet.getvalue(),
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
    )

    assert planning_response.status_code == 200
    assert fleet_response.status_code == 200

    dashboard = client.get("/api/operations/dashboard?reserve_threshold=1")
    assert dashboard.status_code == 200
    payload = dashboard.json()
    assert payload["summary"]["routes"] == 1
    assert payload["capacity"]["operational_vehicles"] == 2
    assert payload["readiness"]["status"] == "green"

    assert client.get("/api/operations/issues").status_code == 200
    assert client.get("/api/operations/capacity").status_code == 200
    assert client.get("/api/operations/readiness").status_code == 200
