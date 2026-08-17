from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from app.core.database import db_session
from app.main import app
from tests.journal_evidence_helpers import MP4, PNG


client = TestClient(app)
BASE = "/api/plugins/fleet/v1/journal"
PHOTO_SLOTS = ("FRONT", "REAR", "LEFT", "RIGHT", "ODOMETER")


def _asset(plate: str = "JH100AA") -> dict:
    response = client.post("/api/plugins/fleet/v1/assets", json={
        "external_identifier": f"evidence-{plate}", "plate": plate,
        "category": "van", "status": "active", "availability": "available",
    })
    assert response.status_code == 201
    return response.json()


def _session(plate: str = "JH100AA", driver: str = "DRV-EVIDENCE") -> dict:
    response = client.post(f"{BASE}/sessions", json={
        "operation_type": "check_out", "plate": plate,
        "declared_driver_identifier": driver, "operational_shift": "morning",
    })
    assert response.status_code == 201
    return response.json()


def _headers(opened: dict) -> dict[str, str]:
    return {"X-Journal-Token": opened["token"]}


def _start(opened: dict, checkpoint: str, mode: str):
    return client.post(
        f"{BASE}/sessions/{opened['id']}/checkpoints/{checkpoint}/start",
        headers=_headers(opened), json={"mode": mode},
    )


def _upload(opened: dict, checkpoint: str, mode: str, slot: str, marker: bytes,
            captured_at: str | None = None):
    video = mode == "VIDEO"
    return client.post(
        f"{BASE}/sessions/{opened['id']}/media", headers=_headers(opened),
        data={
            "checkpoint": checkpoint, "evidence_mode": mode,
            "evidence_slot": slot, "capture_source": "camera",
            **({"captured_at": captured_at} if captured_at else {}),
        },
        files={"file": (
            f"{checkpoint}-{slot}.{'mp4' if video else 'png'}",
            (MP4 if video else PNG) + marker,
            "video/mp4" if video else "image/png",
        )},
    )


def _photo_checkpoint(opened: dict, checkpoint: str, prefix: str = "photo"):
    assert _start(opened, checkpoint, "PHOTO").status_code == 200
    for slot in PHOTO_SLOTS:
        response = _upload(
            opened, checkpoint, "PHOTO", slot,
            f"{prefix}-{checkpoint}-{slot}".encode(),
        )
        assert response.status_code == 201, response.text


def _video_checkpoint(opened: dict, checkpoint: str, prefix: str = "video"):
    assert _start(opened, checkpoint, "VIDEO").status_code == 200
    response = _upload(
        opened, checkpoint, "VIDEO", "VIDEO",
        f"{prefix}-{checkpoint}".encode(),
    )
    assert response.status_code == 201, response.text


def _complete_checkpoint(opened: dict, checkpoint: str):
    return client.post(
        f"{BASE}/sessions/{opened['id']}/checkpoints/{checkpoint}/complete",
        headers=_headers(opened),
    )


def _payload(submission: str) -> dict:
    return {
        "odometer_km": 1234, "fuel_percentage": 70,
        "anomaly_present": False,
        "equipment": [{"code": code, "status": "present"} for code in (
            "telepass", "phone", "keys", "fuel_card"
        )],
        "client_submission_id": submission, "timezone": "Europe/Rome",
    }


def _close(opened: dict, submission: str):
    return client.post(
        f"{BASE}/sessions/{opened['id']}/complete",
        headers=_headers(opened), json=_payload(submission),
    )


def _media_id(session_id: str, checkpoint: str) -> str:
    with db_session() as conn:
        return str(conn.execute(
            "SELECT id FROM movement_media WHERE session_id=? AND checkpoint=?",
            (session_id, checkpoint),
        ).fetchone()["id"])


def test_01_new_journal_requires_check_in():
    _asset(); opened = _session()
    detail = _close(opened, "requires-check-in").json()["detail"]
    assert detail["code"] == "JOURNAL_EVIDENCE_INCOMPLETE"
    assert detail["lifecycle_status"] == "CHECK_IN_REQUIRED"


def test_02_photo_check_in_requires_five_slots():
    _asset(); opened = _session(); _photo_checkpoint(opened, "CHECK_IN")
    report = _complete_checkpoint(opened, "CHECK_IN").json()["evidence"]["checkpoints"]["CHECK_IN"]
    assert report["completed"] is True
    assert report["present_slots"] == sorted(PHOTO_SLOTS)


def test_03_missing_front_blocks_check_in():
    _asset(); opened = _session(); assert _start(opened, "CHECK_IN", "PHOTO").status_code == 200
    for slot in PHOTO_SLOTS[1:]:
        assert _upload(opened, "CHECK_IN", "PHOTO", slot, slot.encode()).status_code == 201
    response = _complete_checkpoint(opened, "CHECK_IN")
    assert response.status_code == 422
    assert response.json()["detail"]["missing_slots"] == ["FRONT"]


def test_04_missing_odometer_blocks_check_in():
    _asset(); opened = _session(); assert _start(opened, "CHECK_IN", "PHOTO").status_code == 200
    for slot in PHOTO_SLOTS[:-1]:
        assert _upload(opened, "CHECK_IN", "PHOTO", slot, slot.encode()).status_code == 201
    assert _complete_checkpoint(opened, "CHECK_IN").json()["detail"]["missing_slots"] == ["ODOMETER"]


def test_05_video_check_in_is_accepted():
    _asset(); opened = _session(); _video_checkpoint(opened, "CHECK_IN")
    assert _complete_checkpoint(opened, "CHECK_IN").status_code == 200


def test_06_mixed_modes_are_allowed_across_checkpoints():
    _asset(); opened = _session(); _photo_checkpoint(opened, "CHECK_IN")
    assert _complete_checkpoint(opened, "CHECK_IN").status_code == 200
    _video_checkpoint(opened, "CHECK_OUT")
    result = _complete_checkpoint(opened, "CHECK_OUT").json()["evidence"]
    assert result["checkpoints"]["CHECK_IN"]["mode"] == "PHOTO"
    assert result["checkpoints"]["CHECK_OUT"]["mode"] == "VIDEO"


def test_07_check_out_is_required_for_close():
    _asset(); opened = _session(); _video_checkpoint(opened, "CHECK_IN")
    assert _complete_checkpoint(opened, "CHECK_IN").status_code == 200
    response = _close(opened, "checkout-required")
    assert response.status_code == 422
    assert response.json()["detail"]["lifecycle_status"] == "CHECK_OUT_REQUIRED"


def test_08_missing_check_out_slot_blocks_close():
    _asset(); opened = _session(); _video_checkpoint(opened, "CHECK_IN")
    assert _complete_checkpoint(opened, "CHECK_IN").status_code == 200
    assert _start(opened, "CHECK_OUT", "PHOTO").status_code == 200
    for slot in PHOTO_SLOTS[:-1]:
        assert _upload(opened, "CHECK_OUT", "PHOTO", slot, slot.encode()).status_code == 201
    assert _complete_checkpoint(opened, "CHECK_OUT").status_code == 422
    assert _close(opened, "checkout-incomplete").status_code == 422


def test_09_photo_check_out_five_of_five():
    _asset(); opened = _session(); _video_checkpoint(opened, "CHECK_IN")
    assert _complete_checkpoint(opened, "CHECK_IN").status_code == 200
    _photo_checkpoint(opened, "CHECK_OUT")
    assert _complete_checkpoint(opened, "CHECK_OUT").status_code == 200


def test_10_video_check_out_allows_close():
    _asset(); opened = _session(); _video_checkpoint(opened, "CHECK_IN")
    assert _complete_checkpoint(opened, "CHECK_IN").status_code == 200
    _video_checkpoint(opened, "CHECK_OUT")
    assert _complete_checkpoint(opened, "CHECK_OUT").status_code == 200
    assert _close(opened, "video-checkout").status_code == 200


def test_11_same_day_mismatch_blocks_checkpoint():
    _asset(); opened = _session(); assert _start(opened, "CHECK_IN", "VIDEO").status_code == 200
    yesterday = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    media = _upload(opened, "CHECK_IN", "VIDEO", "VIDEO", b"old", yesterday).json()
    assert media["freshness_status"] == "DATE_MISMATCH"
    assert _complete_checkpoint(opened, "CHECK_IN").status_code == 422


def test_12_reuse_detection_applies_to_check_in():
    _asset(); first = _session(); _video_checkpoint(first, "CHECK_IN", "same")
    assert _complete_checkpoint(first, "CHECK_IN").status_code == 200
    _video_checkpoint(first, "CHECK_OUT", "first-out")
    assert _complete_checkpoint(first, "CHECK_OUT").status_code == 200
    assert _close(first, "reuse-in-first").status_code == 200
    second = _session(); _video_checkpoint(second, "CHECK_IN", "same")
    assert _complete_checkpoint(second, "CHECK_IN").status_code == 422


def test_13_reuse_detection_applies_to_check_out():
    _asset(); first = _session(); _video_checkpoint(first, "CHECK_IN", "first-in")
    assert _complete_checkpoint(first, "CHECK_IN").status_code == 200
    _video_checkpoint(first, "CHECK_OUT", "same-out")
    assert _complete_checkpoint(first, "CHECK_OUT").status_code == 200
    assert _close(first, "reuse-out-first").status_code == 200
    second = _session(); _video_checkpoint(second, "CHECK_IN", "second-in")
    assert _complete_checkpoint(second, "CHECK_IN").status_code == 200
    _video_checkpoint(second, "CHECK_OUT", "same-out")
    assert _complete_checkpoint(second, "CHECK_OUT").status_code == 422


def test_14_replacement_before_completion_is_slot_scoped():
    _asset(); opened = _session(); assert _start(opened, "CHECK_IN", "PHOTO").status_code == 200
    first = _upload(opened, "CHECK_IN", "PHOTO", "FRONT", b"one").json()
    second = _upload(opened, "CHECK_IN", "PHOTO", "FRONT", b"two").json()
    assert second["replaced_media_id"] == first["id"]
    with db_session() as conn:
        rows = conn.execute(
            "SELECT id FROM movement_media WHERE session_id=? AND checkpoint='CHECK_IN' AND evidence_slot='FRONT'",
            (opened["id"],),
        ).fetchall()
    assert [row["id"] for row in rows] == [second["id"]]


def test_15_checkpoint_is_immutable_after_completion():
    _asset(); opened = _session(); _video_checkpoint(opened, "CHECK_IN")
    assert _complete_checkpoint(opened, "CHECK_IN").status_code == 200
    assert _upload(opened, "CHECK_IN", "VIDEO", "VIDEO", b"replacement").status_code == 409
    response = client.delete(
        f"{BASE}/sessions/{opened['id']}/media/{_media_id(opened['id'], 'CHECK_IN')}",
        headers=_headers(opened),
    )
    assert response.status_code == 409


def test_16_organization_isolation_keeps_reuse_scoped():
    _asset(); first = _session(); _video_checkpoint(first, "CHECK_IN", "org")
    assert _complete_checkpoint(first, "CHECK_IN").status_code == 200
    _video_checkpoint(first, "CHECK_OUT", "org-out")
    assert _complete_checkpoint(first, "CHECK_OUT").status_code == 200
    assert _close(first, "org-isolation-first").status_code == 200
    media_id = _media_id(first["id"], "CHECK_IN")
    with db_session() as conn:
        conn.execute("UPDATE movement_media SET organization_id='other-org' WHERE id=?", (media_id,))
    second = _session(); _video_checkpoint(second, "CHECK_IN", "org")
    assert _complete_checkpoint(second, "CHECK_IN").status_code == 200


def test_17_media_preserves_vehicle_and_driver_binding():
    asset = _asset(); opened = _session(driver="DRV-BIND"); _video_checkpoint(opened, "CHECK_IN")
    with db_session() as conn:
        row = conn.execute("SELECT * FROM movement_media WHERE session_id=?", (opened["id"],)).fetchone()
    assert row["vehicle_id"] == asset["id"]
    assert row["declared_driver_identifier"] == "DRV-BIND"
    assert row["checkpoint"] == "CHECK_IN"


def test_18_historic_journal_is_not_invalidated():
    _asset(); opened = _session()
    with db_session() as conn:
        conn.execute("UPDATE journal_sessions SET evidence_policy_version=NULL WHERE id=?", (opened["id"],))
    assert _close(opened, "historic-compatible").status_code == 200


def test_19_checkpoint_audit_events_are_persisted_without_raw_files():
    _asset(); opened = _session(); _video_checkpoint(opened, "CHECK_IN")
    assert _complete_checkpoint(opened, "CHECK_IN").status_code == 200
    with db_session() as conn:
        rows = conn.execute(
            "SELECT * FROM journal_checkpoint_events WHERE session_id=? ORDER BY created_at",
            (opened["id"],),
        ).fetchall()
    assert [row["event_type"] for row in rows] == [
        "journal_check_in_started", "journal_check_in_completed",
    ]
    assert all("raw" not in row.keys() for row in rows)


def test_20_failed_final_gate_creates_no_movement_transactionally():
    _asset(); opened = _session(); _video_checkpoint(opened, "CHECK_IN")
    assert _complete_checkpoint(opened, "CHECK_IN").status_code == 200
    assert _close(opened, "no-partial-write").status_code == 422
    with db_session() as conn:
        movement = conn.execute("SELECT id FROM asset_movements WHERE session_id=?", (opened["id"],)).fetchone()
        status = conn.execute("SELECT status FROM journal_sessions WHERE id=?", (opened["id"],)).fetchone()
    assert movement is None
    assert status["status"] == "open"
