from fastapi.testclient import TestClient

from app.core.database import db_session
from app.main import app
from app.plugins.fleet.journal.infrastructure.shared_access_repository import (
    init_schema as init_shared_access_schema,
)


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


def _legacy_row(row_id: str, token: str, created_at: str, organization_id=None):
    with db_session() as conn:
        conn.execute(
            """
            INSERT INTO journal_shared_access (
                id, token, status, created_at, organization_id
            ) VALUES (?, ?, 'active', ?, ?)
            """,
            (row_id, token, created_at, organization_id),
        )


def test_legacy_assignment_revokes_a_duplicate_when_owner_has_active_link():
    with db_session() as conn:
        conn.execute(
            "INSERT INTO organizations (id, name, created_at) VALUES (?, ?, ?)",
            ("owner-org", "Owner", "2026-01-01T00:00:00Z"),
        )
    _legacy_row("current", "token-current", "2026-02-01T00:00:00Z", "owner-org")
    _legacy_row("legacy", "token-legacy", "2026-01-01T00:00:00Z")

    init_shared_access_schema()

    with db_session() as conn:
        rows = conn.execute(
            "SELECT id, status, organization_id FROM journal_shared_access ORDER BY id"
        ).fetchall()
    by_id = {row["id"]: row for row in rows}
    assert by_id["current"]["status"] == "active"
    assert by_id["legacy"]["status"] == "revoked"
    assert by_id["legacy"]["organization_id"] == "owner-org"


def test_legacy_assignment_keeps_only_the_newest_active_link():
    with db_session() as conn:
        conn.execute(
            "INSERT INTO organizations (id, name, created_at) VALUES (?, ?, ?)",
            ("owner-org", "Owner", "2026-01-01T00:00:00Z"),
        )
    _legacy_row("older", "token-older", "2026-01-01T00:00:00Z")
    _legacy_row("newer", "token-newer", "2026-02-01T00:00:00Z")

    init_shared_access_schema()

    with db_session() as conn:
        rows = conn.execute(
            "SELECT id, status, organization_id FROM journal_shared_access ORDER BY id"
        ).fetchall()
    by_id = {row["id"]: row for row in rows}
    assert by_id["newer"]["status"] == "active"
    assert by_id["older"]["status"] == "revoked"
    assert {row["organization_id"] for row in rows} == {"owner-org"}


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


def test_public_vehicle_lookup_uses_shared_token_organization_context():
    expected = create_asset()
    access = client.post(f"{CONTROL}/shared-access", json={}).json()
    with db_session() as conn:
        conn.execute(
            "INSERT INTO organizations (id, name, created_at) VALUES (?, ?, ?)",
            ("foreign-journal-org", "Foreign Journal", "2026-08-08T10:00:00Z"),
        )
        conn.execute(
            """
            INSERT INTO fleet_assets (
                organization_id, external_identifier, plate, category, status,
                availability, capabilities, created_at, updated_at
            ) VALUES (?, ?, ?, 'Furgone', 'active', 'available', '[]', ?, ?)
            """,
            (
                "foreign-journal-org",
                "FOREIGN-SHARED-ASSET",
                "FOREIGN1",
                "2026-08-08T10:00:00Z",
                "2026-08-08T10:00:00Z",
            ),
        )

    found = client.get(f"{JOURNAL}/assets", params={
        "plate": "SG001AA",
        "access_token": access["token"],
    })
    foreign = client.get(f"{JOURNAL}/assets", params={
        "plate": "FOREIGN1",
        "access_token": access["token"],
    })
    listed = client.get(f"{JOURNAL}/assets", params={
        "access_token": access["token"],
    })

    assert found.status_code == 200
    assert found.json()["id"] == expected["id"]
    assert foreign.status_code == 404
    assert [item["id"] for item in listed.json()["items"]] == [expected["id"]]


def test_shared_entry_page_revalidates_and_serves_new_mobile_module_version():
    access = client.post(f"{CONTROL}/shared-access", json={}).json()

    response = client.get(access["link_path"])

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-cache"
    assert "index.js?v=djh2" in response.text
    assert "shell.js?v=djh2" in response.text
