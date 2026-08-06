import io
import json

from fastapi.testclient import TestClient
from openpyxl import Workbook

from app.main import app


AUTH_HEADERS = {"X-Auth-Enforce": "1"}


def organization_client(name: str, email: str) -> TestClient:
    client = TestClient(app, headers=AUTH_HEADERS)
    registered = client.post(
        "/api/auth/register",
        json={
            "organization": {
                "name": name,
                "primary_station": "DLO2",
                "timezone": "Europe/Rome",
                "language": "it",
            },
            "administrator": {
                "first_name": "Tenant",
                "last_name": "Administrator",
                "email": email,
                "password": "Password-sicura-123",
                "password_confirmation": "Password-sicura-123",
            },
        },
    )
    assert registered.status_code == 201
    return client


def create_asset(client: TestClient) -> dict:
    response = client.post(
        "/api/plugins/fleet/v1/assets",
        json={
            "external_identifier": "tenant-a-vehicle",
            "plate": "TA001AA",
            "category": "Furgone",
            "status": "active",
            "availability": "disponibile",
            "notes": "Visible only to Tenant A",
            "capabilities": [],
        },
    )
    assert response.status_code == 201
    return response.json()


def fleet_identity_book() -> bytes:
    book = Workbook()
    sheet = book.active
    sheet.title = "Stato parco"
    sheet.append(["Asset ID", "Targa", "Modello", "Stato"])
    sheet.append(["tenant-a-vehicle", "TA001AA", "Furgone", "Disponibile"])
    output = io.BytesIO()
    book.save(output)
    book.close()
    return output.getvalue()


def test_operational_data_is_isolated_between_organizations():
    tenant_a = organization_client("Tenant A", "tenant-a@example.test")
    asset = create_asset(tenant_a)

    tenant_b = organization_client("Tenant B", "tenant-b@example.test")

    assert tenant_a.get("/api/plugins/fleet/v1/assets").json()["items"][0]["id"] == asset["id"]
    assert tenant_b.get("/api/plugins/fleet/v1/assets").json()["items"] == []
    assert tenant_b.get(f"/api/plugins/fleet/v1/assets/{asset['id']}").status_code == 404
    assert tenant_b.patch(
        f"/api/plugins/fleet/v1/assets/{asset['id']}",
        json={"notes": "cross-tenant write"},
    ).status_code == 404

    assert tenant_b.get("/api/fleet/damage-cases").json()["items"] == []
    assert tenant_b.get("/api/fleet/maintenances").json()["items"] == []
    assert tenant_b.get("/api/fleet/insurance-policies").json()["items"] == []
    assert tenant_b.get("/api/fleet/franchises").json()["items"] == []
    assert tenant_b.get("/api/fleet/rentals").json()["items"] == []
    assert tenant_b.get("/api/fleet/deadlines").json()["items"] == []
    assert tenant_b.get("/api/fleet/vision").json()["items"] == []
    assert tenant_b.get("/api/plugins/workforce/v1/members").json()["items"] == []

    workspace_b = tenant_b.get("/api/workspace/v1/status")
    assert workspace_b.status_code == 200
    assert workspace_b.json()["workspace_state"] == "EMPTY"
    assert workspace_b.json()["asset_count"] == 0
    assert workspace_b.json()["workforce_member_count"] == 0

    workspace_a = tenant_a.get("/api/workspace/v1/status")
    assert workspace_a.status_code == 200
    assert workspace_a.json()["workspace_state"] == "PRODUCTION"
    assert workspace_a.json()["asset_count"] == 1

    reset_b = tenant_b.post("/api/workspace/v1/reset")
    assert reset_b.status_code == 200
    assert reset_b.json()["idempotent"] is True
    assert tenant_a.get("/api/plugins/fleet/v1/assets").json()["items"][0]["id"] == asset["id"]

    foreign_document = tenant_b.post(
        "/api/fleet/documents",
        json={
            "vehicle_id": asset["id"],
            "document_type": "altro",
            "title": "Documento non autorizzato",
        },
    )
    assert foreign_document.status_code == 404


def test_vehicle_identity_is_unique_inside_each_organization_only():
    tenant_a = organization_client("Identity Tenant A", "identity-a@example.test")
    tenant_b = organization_client("Identity Tenant B", "identity-b@example.test")

    asset_a = create_asset(tenant_a)
    asset_b = create_asset(tenant_b)

    assert asset_a["id"] != asset_b["id"]
    assert asset_a["external_identifier"] == asset_b["external_identifier"]
    assert asset_a["plate"] == asset_b["plate"]
    assert tenant_a.get("/api/plugins/fleet/v1/assets").json()["items"] == [asset_a]
    assert tenant_b.get("/api/plugins/fleet/v1/assets").json()["items"] == [asset_b]

    duplicate_in_tenant_b = tenant_b.post(
        "/api/plugins/fleet/v1/assets",
        json={
            "external_identifier": asset_b["external_identifier"],
            "plate": asset_b["plate"],
            "category": "Furgone",
            "status": "active",
            "availability": "disponibile",
            "notes": None,
            "capabilities": [],
        },
    )
    assert duplicate_in_tenant_b.status_code == 409


def test_fleet_sync_can_import_an_identity_owned_by_another_organization():
    tenant_a = organization_client("Sync Identity Tenant A", "sync-identity-a@example.test")
    tenant_b = organization_client("Sync Identity Tenant B", "sync-identity-b@example.test")
    asset_a = create_asset(tenant_a)
    content = fleet_identity_book()
    upload = {
        "file": (
            "tenant-fleet.xlsx",
            content,
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    }

    proposal_response = tenant_b.post(
        "/api/plugins/fleet/v1/sync/preview",
        files=upload,
    )
    assert proposal_response.status_code == 200
    proposal = proposal_response.json()
    assert proposal["items"][0]["action"] == "NEW_ASSET"

    confirmation = tenant_b.post(
        "/api/plugins/fleet/v1/sync/confirm",
        data={
            "confirmed_fingerprint": proposal["fingerprint"],
            "selected_rows": json.dumps([proposal["items"][0]["row_id"]]),
        },
        files=upload,
    )

    assert confirmation.status_code == 200
    assert confirmation.json()["created_assets"] == 1
    asset_b = tenant_b.get("/api/plugins/fleet/v1/assets").json()["items"][0]
    assert asset_b["id"] != asset_a["id"]
    assert asset_b["external_identifier"] == asset_a["external_identifier"]
    assert asset_b["plate"] == asset_a["plate"]


def test_public_journal_cannot_enumerate_an_organization_fleet():
    tenant = organization_client("Protected Tenant", "protected@example.test")
    create_asset(tenant)

    anonymous = TestClient(app, headers=AUTH_HEADERS)
    assert anonymous.get("/api/plugins/fleet/v1/assets").status_code == 401
    assert anonymous.get(
        "/api/plugins/fleet/v1/journal/assets",
        params={"plate": "TA001AA", "access_token": "invalid"},
    ).status_code in {404, 410}
    assert anonymous.post(
        "/api/plugins/fleet/v1/journal/sessions/shared",
        json={
            "driver_name": "Mario",
            "driver_surname": "Rossi",
            "vehicle_plate": "TA001AA",
            "procedure_type": "check_out",
        },
    ).status_code == 403
