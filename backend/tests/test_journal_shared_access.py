from fastapi.testclient import TestClient

from app.core.database import db_session
from app.main import app


client = TestClient(app)
BASE = "/api/plugins/fleet/v1"
JOURNAL = f"{BASE}/journal"
CONTROL = "/api/fleet/journal-control-room"


def create_asset():
    return client.post(f"{BASE}/assets", json={
        "external_identifier": "SHARED-GDB-001",
        "plate": "SG001AA",
        "category": "Furgone",
        "status": "active",
        "availability": "available",
        "capabilities": [],
    }).json()


def create_driver_session(token: str, name: str):
    response = client.post(f"{JOURNAL}/sessions/shared", json={
        "driver_name": name,
        "driver_surname": "Driver",
        "vehicle_plate": "SG001AA",
        "procedure_type": "check_out",
        "access_token": token,
    })
    assert response.status_code == 201
    return response.json()


def test_single_active_link_public_validation_and_regeneration():
    created = client.post(f"{CONTROL}/shared-access", json={}).json()
    same = client.post(f"{CONTROL}/shared-access", json={}).json()
    assert same["id"] == created["id"]
    assert same["token"] == created["token"]
    assert created["status"] == "active"
    assert created["link_path"].endswith(created["token"])
    assert client.get(f"{JOURNAL}/shared-access/{created['token']}").status_code == 200
    assert client.get(created["link_path"]).status_code == 200

    replacement = client.post(
        f"{CONTROL}/shared-access", json={"regenerate": True}
    ).json()
    assert replacement["id"] != created["id"]
    assert replacement["token"] != created["token"]
    assert client.get(f"{JOURNAL}/shared-access/{created['token']}").status_code == 404
    assert client.get(f"{JOURNAL}/shared-access/{replacement['token']}").status_code == 200


def test_revoked_or_unknown_token_cannot_create_session():
    create_asset()
    access = client.post(f"{CONTROL}/shared-access", json={}).json()
    revoked = client.post(f"{CONTROL}/shared-access/{access['id']}/revoke")
    assert revoked.status_code == 200
    assert revoked.json()["status"] == "revoked"
    assert client.get(f"{JOURNAL}/shared-access/{access['token']}").status_code == 404
    assert client.get(f"{JOURNAL}/shared-access/not-a-real-token").status_code == 404
    denied = client.post(f"{JOURNAL}/sessions/shared", json={
        "driver_name": "Mario",
        "driver_surname": "Rossi",
        "vehicle_plate": "SG001AA",
        "procedure_type": "check_out",
        "access_token": access["token"],
    })
    assert denied.status_code == 404, denied.text


def test_two_drivers_share_entry_link_but_get_distinct_sessions():
    vehicle = create_asset()
    access = client.post(f"{CONTROL}/shared-access", json={}).json()
    first = create_driver_session(access["token"], "Mario")
    second = create_driver_session(access["token"], "Luigi")
    assert first["session_id"] != second["session_id"]
    assert first["token"] != second["token"]
    payload = client.get(CONTROL).json()
    ids = {item["id"] for item in payload["items"]}
    assert {first["session_id"], second["session_id"]} <= ids
    assert all(
        item["source"] == "shared_link"
        for item in payload["items"]
        if item["id"] in {first["session_id"], second["session_id"]}
    )
    with db_session() as conn:
        assert conn.execute(
            "SELECT COUNT(*) FROM journal_sessions WHERE asset_id = ?",
            (vehicle["id"],),
        ).fetchone()[0] == 2
        assert conn.execute(
            "SELECT COUNT(*) FROM journal_shared_access WHERE status = 'active'"
        ).fetchone()[0] == 1
