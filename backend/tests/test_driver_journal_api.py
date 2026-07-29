import base64
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from app.core.database import db_session
from app.main import app


client = TestClient(app)
BASE = "/api/plugins/fleet/v1/journal"
PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk"
    "YAAAAAYAAjCB0C8AAAAASUVORK5CYII="
)


def asset(plate="AB 123-CD"):
    response = client.post(
        "/api/plugins/fleet/v1/assets",
        json={
            "external_identifier": f"asset-{plate}",
            "plate": plate,
            "category": "van",
            "status": "active",
            "availability": "available",
        },
    )
    assert response.status_code == 201
    return response.json()


def session(operation="check_out", plate="AB123CD"):
    response = client.post(
        f"{BASE}/sessions",
        json={
            "operation_type": operation,
            "plate": plate,
            "declared_driver_identifier": "DRV-001",
            "operational_shift": "morning" if operation == "check_out" else None,
        },
    )
    assert response.status_code == 201
    return response.json()


def payload(operation="check_out", submission="submission-001"):
    return {
        "odometer_km": 1234,
        "fuel_percentage": 75,
        "cleanliness_status": "compliant" if operation == "check_in" else None,
        "anomaly_present": False,
        "equipment": [
            {"code": "telepass", "status": "present"},
            {"code": "phone", "status": "present"},
            {"code": "keys", "status": "present"},
            {"code": "fuel_card", "status": "present"},
        ],
        "client_submission_id": submission,
        "timezone": "Europe/Rome",
    }


def complete(open_session, body):
    return client.post(
        f"{BASE}/sessions/{open_session['id']}/complete",
        headers={"X-Journal-Token": open_session["token"]},
        json=body,
    )


def test_configuration_is_public_and_checklist_configurable():
    response = client.get(f"{BASE}/configuration")
    assert response.status_code == 200
    config = response.json()
    assert [item["code"] for item in config["equipment"]] == [
        "telepass", "phone", "keys", "fuel_card"
    ]
    assert config["media"]["video_enabled"] is False


def test_plate_is_normalized_and_asset_registry_is_not_listed():
    created = asset()
    response = client.get(f"{BASE}/assets", params={"plate": " ab-123 cd "})
    assert response.status_code == 200
    assert response.json()["id"] == created["id"]
    assert "documents" not in response.json()


def test_unknown_asset_and_checkout_without_shift_are_rejected():
    missing = client.get(f"{BASE}/assets", params={"plate": "ZZ999ZZ"})
    assert missing.status_code == 404
    asset()
    invalid = client.post(
        f"{BASE}/sessions",
        json={
            "operation_type": "check_out", "plate": "AB123CD",
            "declared_driver_identifier": "DRV-001",
        },
    )
    assert invalid.status_code == 422


def test_valid_checkout_and_minimal_receipt():
    asset()
    opened = session()
    assert "token_hash" not in opened
    response = complete(opened, payload())
    assert response.status_code == 200
    receipt = response.json()
    assert receipt["operation_type"] == "check_out"
    assert receipt["verification_id"].startswith("JM-")
    assert "declared_driver_identifier" not in receipt


def test_valid_checkin_requires_cleanliness():
    asset()
    opened = session("check_in")
    invalid = payload("check_in")
    invalid["cleanliness_status"] = None
    assert complete(opened, invalid).status_code == 422
    valid = complete(opened, payload("check_in"))
    assert valid.status_code == 200
    assert valid.json()["cleanliness_status"] == "compliant"


def test_conditional_anomaly_description_km_fuel_and_checklist():
    asset()
    cases = [
        ({"odometer_km": -1}, 422),
        ({"fuel_percentage": 101}, 422),
        ({"anomaly_present": True, "anomaly_description": ""}, 422),
        ({"equipment": payload()["equipment"][:-1]}, 422),
    ]
    for index, (changes, expected) in enumerate(cases):
        opened = session()
        body = payload(submission=f"submission-invalid-{index}")
        body.update(changes)
        assert complete(opened, body).status_code == expected


def test_wrong_token_expired_and_completed_session_reuse():
    asset()
    opened = session()
    wrong = client.post(
        f"{BASE}/sessions/{opened['id']}/complete",
        headers={"X-Journal-Token": "wrong"},
        json=payload(),
    )
    assert wrong.status_code == 403
    with db_session() as conn:
        conn.execute(
            "UPDATE journal_sessions SET expires_at = ? WHERE id = ?",
            ((datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat(), opened["id"]),
        )
    assert complete(opened, payload()).status_code == 410

    opened = session()
    assert complete(opened, payload(submission="reuse-first")).status_code == 200
    assert complete(opened, payload(submission="reuse-other")).status_code == 409


def test_double_submission_is_idempotent_and_append_only():
    asset()
    opened = session()
    first = complete(opened, payload())
    second = complete(opened, payload())
    assert first.status_code == second.status_code == 200
    assert first.json()["id"] == second.json()["id"]
    with db_session() as conn:
        assert conn.execute("SELECT COUNT(*) FROM asset_movements").fetchone()[0] == 1
        with_exception = False
        try:
            conn.execute(
                "INSERT INTO asset_movements (id) VALUES ('invalid')"
            )
        except Exception:
            with_exception = True
    assert with_exception


def test_image_upload_remove_and_private_cross_session_access():
    asset()
    first = session()
    second = session()
    uploaded = client.post(
        f"{BASE}/sessions/{first['id']}/media",
        headers={"X-Journal-Token": first["token"]},
        files={"file": ("proof.png", PNG, "image/png")},
    )
    assert uploaded.status_code == 201
    media_id = uploaded.json()["id"]
    forbidden = client.delete(
        f"{BASE}/sessions/{second['id']}/media/{media_id}",
        headers={"X-Journal-Token": second["token"]},
    )
    assert forbidden.status_code == 404
    removed = client.delete(
        f"{BASE}/sessions/{first['id']}/media/{media_id}",
        headers={"X-Journal-Token": first["token"]},
    )
    assert removed.status_code == 204


def test_media_rejects_false_mime_corruption_and_size_limit():
    asset()
    opened = session()
    headers = {"X-Journal-Token": opened["token"]}
    false_mime = client.post(
        f"{BASE}/sessions/{opened['id']}/media", headers=headers,
        files={"file": ("proof.jpg", PNG, "image/jpeg")},
    )
    corrupt = client.post(
        f"{BASE}/sessions/{opened['id']}/media", headers=headers,
        files={"file": ("proof.png", b"not-an-image", "image/png")},
    )
    oversized = client.post(
        f"{BASE}/sessions/{opened['id']}/media", headers=headers,
        files={"file": ("proof.png", PNG + b"x" * (8 * 1024 * 1024), "image/png")},
    )
    assert false_mime.status_code == corrupt.status_code == oversized.status_code == 422


def test_uploaded_photo_is_attached_to_movement_atomically():
    asset()
    opened = session()
    upload = client.post(
        f"{BASE}/sessions/{opened['id']}/media",
        headers={"X-Journal-Token": opened["token"]},
        files={"file": ("proof.png", PNG, "image/png")},
    )
    assert upload.status_code == 201
    receipt = complete(opened, payload()).json()
    assert len(receipt["media"]) == 1
    with db_session() as conn:
        row = conn.execute(
            "SELECT movement_id FROM movement_media WHERE id = ?",
            (upload.json()["id"],),
        ).fetchone()
    assert row["movement_id"] == receipt["id"]


def test_receipt_endpoint_and_no_public_list_routes():
    asset()
    opened = session()
    movement = complete(opened, payload()).json()
    receipt = client.get(f"{BASE}/movements/{movement['id']}/receipt")
    assert receipt.status_code == 200
    assert client.get(f"{BASE}/movements").status_code == 404
    assert client.get(f"{BASE}/drivers").status_code == 404
