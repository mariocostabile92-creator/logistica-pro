import base64
from datetime import datetime, timezone

from fastapi.testclient import TestClient

from app.core.database import db_session
from app.main import app
from app.auth.domain import Role
from app.auth.permission_service import has_permission
from app.plugins.fleet.journal.domain.operational_day import operational_date
from app.plugins.fleet.journal.infrastructure.storage import PrivateLocalMediaStorage


client = TestClient(app)
BASE = "/api/plugins/fleet/v1/journal"
PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=")
MP4 = b"\x00\x00\x00\x18ftypisom\x00\x00\x02\x00isomiso2"


def asset():
    return client.post("/api/plugins/fleet/v1/assets", json={
        "external_identifier": "P04-001", "plate": "P004AA", "category": "Van",
        "status": "active", "availability": "available", "capabilities": [],
    }).json()


def session():
    vehicle = asset()
    response = client.post(f"{BASE}/sessions", json={
        "operation_type": "check_in", "plate": vehicle["plate"],
        "declared_driver_identifier": "Mario Rossi", "operational_shift": None,
    })
    assert response.status_code == 201
    return vehicle, response.json()


def test_image_video_relative_keys_atomic_restart_and_download():
    vehicle, opened = session()
    headers = {"X-Journal-Token": opened["token"]}
    image = client.post(f"{BASE}/sessions/{opened['id']}/media", headers=headers,
                        files={"file": ("prova.png", PNG, "image/png")})
    video = client.post(f"{BASE}/sessions/{opened['id']}/media", headers=headers,
                        files={"file": ("prova.mp4", MP4, "video/mp4")})
    assert image.status_code == video.status_code == 201
    with db_session() as conn:
        rows = conn.execute("SELECT * FROM movement_media ORDER BY display_order").fetchall()
    assert [row["media_type"] for row in rows] == ["image", "video"]
    assert all(not row["storage_key"].startswith(("/", "C:")) for row in rows)
    assert all(row["organization_id"] == "test-organization" for row in rows)
    assert all(row["vehicle_id"] == vehicle["id"] for row in rows)
    live = client.get("/api/fleet/journal-control-room").json()["items"][0]
    assert [entry["original_filename"] for entry in live["media"]] == ["prova.png", "prova.mp4"]
    assert all(entry["uploaded_at"] for entry in live["media"])
    restarted = PrivateLocalMediaStorage()
    assert all(restarted.path(row["storage_key"]).read_bytes() in {PNG, MP4} for row in rows)
    assert not list(restarted.path(rows[0]["storage_key"]).parent.glob("*.tmp"))
    admin = client.get(f"/api/fleet/journal-control-room/media/{video.json()['id']}?download=1")
    assert admin.status_code == 200
    assert "attachment" in admin.headers["content-disposition"]


def test_video_extension_mime_and_path_traversal_are_rejected():
    _, opened = session()
    headers = {"X-Journal-Token": opened["token"]}
    wrong_extension = client.post(f"{BASE}/sessions/{opened['id']}/media", headers=headers,
                                  files={"file": ("prova.jpg", MP4, "video/mp4")})
    wrong_mime = client.post(f"{BASE}/sessions/{opened['id']}/media", headers=headers,
                             files={"file": ("prova.mp4", MP4, "image/png")})
    assert wrong_extension.status_code == wrong_mime.status_code == 422
    storage = PrivateLocalMediaStorage()
    try:
        storage.save("../escape.mp4", MP4)
        assert False, "path traversal accepted"
    except RuntimeError:
        pass


def test_operational_day_after_midnight_and_archive_queries():
    assert operational_date(datetime(2026, 8, 2, 1, 30, tzinfo=timezone.utc), "Europe/Rome", 4).isoformat() == "2026-08-01"
    vehicle, opened = session()
    with db_session() as conn:
        conn.execute("UPDATE journal_sessions SET operational_date='2026-08-01' WHERE id=?", (opened["id"],))
    month = client.get("/api/fleet/journal-archive/month", params={"month": "2026-08"})
    day = client.get("/api/fleet/journal-archive/day", params={"date": "2026-08-01", "search": vehicle["plate"]})
    assert month.status_code == day.status_code == 200
    assert month.json()["days"][0]["incomplete"] == 1
    assert month.json()["context"]["timezone"] == "Europe/Rome"
    assert day.json()["summary"]["incomplete"] == 1
    current_month = client.get("/api/fleet/journal-archive/month")
    assert current_month.status_code == 200
    assert current_month.json()["month"] == current_month.json()["context"]["operational_date"][:7]


def test_cross_organization_media_and_archive_are_not_visible():
    _, opened = session()
    upload = client.post(f"{BASE}/sessions/{opened['id']}/media",
                         headers={"X-Journal-Token": opened["token"]},
                         files={"file": ("prova.png", PNG, "image/png")}).json()
    with db_session() as conn:
        conn.execute("UPDATE movement_media SET organization_id='other' WHERE id=?", (upload["id"],))
        conn.execute("UPDATE journal_sessions SET organization_id='other' WHERE id=?", (opened["id"],))
    assert client.get(f"/api/fleet/journal-control-room/media/{upload['id']}").status_code == 404
    assert client.get("/api/fleet/journal-archive/day", params={"date": datetime.now().date().isoformat()}).json()["total"] == 0


def test_media_permissions_public_token_and_administrative_delete():
    _, opened = session()
    uploaded = client.post(f"{BASE}/sessions/{opened['id']}/media",
                           headers={"X-Journal-Token": opened["token"]},
                           files={"file": ("prova.png", PNG, "image/png")}).json()
    assert client.get(f"{BASE}/media/{uploaded['id']}").status_code == 403
    assert client.get(f"{BASE}/media/{uploaded['id']}", params={"token": opened["token"]}).status_code == 200
    assert has_permission(Role.VIEWER, "journal:read")
    assert not has_permission(Role.VIEWER, "journal:media:delete")
    assert has_permission(Role.FLEET_MANAGER, "journal:media:delete")
    deleted = client.delete(f"/api/fleet/journal-control-room/media/{uploaded['id']}")
    assert deleted.status_code == 204
    with db_session() as conn:
        assert conn.execute("SELECT 1 FROM movement_media WHERE id=?", (uploaded["id"],)).fetchone() is None


def test_integrity_report_never_exposes_absolute_paths():
    _, opened = session()
    client.post(f"{BASE}/sessions/{opened['id']}/media",
                headers={"X-Journal-Token": opened["token"]},
                files={"file": ("prova.png", PNG, "image/png")})
    response = client.get("/api/fleet/journal-integrity")
    assert response.status_code == 200
    assert response.json()["missing_files"] == []
    assert "journal_media" not in response.text
