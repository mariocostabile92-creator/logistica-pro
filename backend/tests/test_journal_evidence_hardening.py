from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from app.core.database import db_session
from app.main import app
from tests.journal_evidence_helpers import MP4, PNG


client = TestClient(app)
BASE = "/api/plugins/fleet/v1/journal"


def _asset(plate: str = "JH100AA") -> dict:
    response = client.post("/api/plugins/fleet/v1/assets", json={
        "external_identifier": f"evidence-{plate}",
        "plate": plate,
        "category": "van",
        "status": "active",
        "availability": "available",
    })
    assert response.status_code == 201
    return response.json()


def _session(plate: str = "JH100AA", driver: str = "DRV-EVIDENCE") -> dict:
    response = client.post(f"{BASE}/sessions", json={
        "operation_type": "check_out",
        "plate": plate,
        "declared_driver_identifier": driver,
        "operational_shift": "morning",
    })
    assert response.status_code == 201
    return response.json()


def _payload(submission: str) -> dict:
    return {
        "odometer_km": 1234,
        "fuel_percentage": 70,
        "anomaly_present": False,
        "equipment": [
            {"code": code, "status": "present"}
            for code in ("telepass", "phone", "keys", "fuel_card")
        ],
        "client_submission_id": submission,
        "timezone": "Europe/Rome",
    }


def _upload(
    opened: dict,
    *,
    kind: str,
    marker: bytes,
    captured_at: str | None = None,
    capture_source: str = "camera",
) -> dict:
    video = kind == "video"
    response = client.post(
        f"{BASE}/sessions/{opened['id']}/media",
        headers={"X-Journal-Token": opened["token"]},
        data={
            "capture_source": capture_source,
            "evidence_slot": kind,
            **({"captured_at": captured_at} if captured_at else {}),
        },
        files={"file": (
            f"evidence.{'mp4' if video else 'png'}",
            (MP4 if video else PNG) + marker,
            "video/mp4" if video else "image/png",
        )},
    )
    assert response.status_code == 201, response.text
    return response.json()


def _complete(opened: dict, submission: str):
    return client.post(
        f"{BASE}/sessions/{opened['id']}/complete",
        headers={"X-Journal-Token": opened["token"]},
        json=_payload(submission),
    )


def test_completion_without_photo_is_rejected_with_structured_missing_evidence():
    _asset()
    opened = _session()
    _upload(opened, kind="video", marker=b"video-only")
    response = _complete(opened, "missing-photo")
    assert response.status_code == 422
    detail = response.json()["detail"]
    assert detail["code"] == "JOURNAL_EVIDENCE_INCOMPLETE"
    assert detail["missing"] == [{"evidence_type": "photo", "required": 1, "present": 0}]


def test_completion_without_video_is_rejected():
    _asset()
    opened = _session()
    _upload(opened, kind="photo", marker=b"photo-only")
    detail = _complete(opened, "missing-video").json()["detail"]
    assert detail["missing"][0]["evidence_type"] == "video"


def test_complete_evidence_is_accepted_and_server_received_at_is_authoritative():
    _asset()
    opened = _session()
    captured = datetime.now(timezone.utc).isoformat()
    photo = _upload(opened, kind="photo", marker=b"complete-photo", captured_at=captured)
    video = _upload(opened, kind="video", marker=b"complete-video", captured_at=captured)
    response = _complete(opened, "complete-evidence")
    assert response.status_code == 200, response.text
    assert photo["received_at"] and video["received_at"]
    assert photo["freshness_status"] == "VERIFIED_SESSION_CAPTURE"
    assert photo["operational_date"]


def test_date_mismatch_is_deterministic_and_blocks_completion():
    _asset()
    opened = _session()
    yesterday = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    photo = _upload(opened, kind="photo", marker=b"old-date", captured_at=yesterday)
    _upload(opened, kind="video", marker=b"valid-video", captured_at=datetime.now(timezone.utc).isoformat())
    assert photo["freshness_status"] == "DATE_MISMATCH"
    assert "non coerente" in photo["freshness_warning"]
    detail = _complete(opened, "date-mismatch").json()["detail"]
    assert detail["blocked"][0]["code"] == "DATE_MISMATCH"


def test_reused_hash_is_scoped_detected_and_blocks_second_journal():
    _asset()
    first = _session()
    captured = datetime.now(timezone.utc).isoformat()
    _upload(first, kind="photo", marker=b"reused", captured_at=captured)
    _upload(first, kind="video", marker=b"first-video", captured_at=captured)
    assert _complete(first, "reuse-first").status_code == 200

    second = _session()
    reused = _upload(second, kind="photo", marker=b"reused", captured_at=captured)
    _upload(second, kind="video", marker=b"second-video", captured_at=captured)
    assert reused["reuse_detected"] == 1
    detail = _complete(second, "reuse-second").json()["detail"]
    assert any(item["code"] == "REUSED_EVIDENCE" for item in detail["blocked"])


def test_replacement_before_completion_removes_previous_slot():
    _asset()
    opened = _session()
    first = _upload(opened, kind="photo", marker=b"replace-a")
    second = _upload(opened, kind="photo", marker=b"replace-b")
    assert second["replaced_media_id"] == first["id"]
    with db_session() as conn:
        rows = conn.execute(
            "SELECT id FROM movement_media WHERE session_id = ? AND evidence_slot = 'photo'",
            (opened["id"],),
        ).fetchall()
    assert [row["id"] for row in rows] == [second["id"]]


def test_evidence_is_immutable_after_completion_and_media_token_is_private():
    _asset()
    first = _session()
    second = _session(driver="DRV-OTHER")
    photo = _upload(first, kind="photo", marker=b"private-photo")
    _upload(first, kind="video", marker=b"private-video")
    assert _complete(first, "immutable").status_code == 200
    replace = client.post(
        f"{BASE}/sessions/{first['id']}/media",
        headers={"X-Journal-Token": first["token"]},
        data={"capture_source": "camera", "evidence_slot": "photo"},
        files={"file": ("new.png", PNG + b"new", "image/png")},
    )
    assert replace.status_code == 409
    assert client.get(
        f"{BASE}/media/{photo['id']}", params={"token": second["token"]}
    ).status_code == 403


def test_historical_session_without_policy_remains_compatible():
    _asset()
    opened = _session()
    with db_session() as conn:
        conn.execute(
            "UPDATE journal_sessions SET evidence_policy_version = NULL WHERE id = ?",
            (opened["id"],),
        )
    assert _complete(opened, "historical-compatible").status_code == 200


def test_reuse_detection_does_not_cross_organization_boundary():
    _asset()
    first = _session()
    photo = _upload(first, kind="photo", marker=b"org-scoped")
    _upload(first, kind="video", marker=b"org-scoped-video")
    assert _complete(first, "org-scoped-first").status_code == 200
    with db_session() as conn:
        conn.execute("UPDATE movement_media SET organization_id='other-org' WHERE id=?", (photo["id"],))
    second = _session()
    own = _upload(second, kind="photo", marker=b"org-scoped")
    assert own["reuse_detected"] == 0
