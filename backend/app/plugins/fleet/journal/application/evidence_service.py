from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.plugins.fleet.journal.domain.models import EvidenceFreshnessStatus


CHECKPOINTS = ("CHECK_IN", "CHECK_OUT")
EVIDENCE_MODES = ("PHOTO", "VIDEO")
PHOTO_SLOTS = ("FRONT", "REAR", "LEFT", "RIGHT", "ODOMETER")
VIDEO_SLOT = "VIDEO"
REQUIRED_EVIDENCE = {
    "PHOTO": list(PHOTO_SLOTS),
    "VIDEO": [VIDEO_SLOT],
}
EVIDENCE_POLICY_VERSION = "2.0"
ALLOWED_CAPTURE_SOURCES = {"camera", "file"}


def checkpoint_column(checkpoint: str, suffix: str) -> str:
    if checkpoint not in CHECKPOINTS:
        raise ValueError("Checkpoint evidenza non valido.")
    if suffix not in {"mode", "started_at", "completed_at"}:
        raise ValueError("Campo checkpoint non valido.")
    return f"{checkpoint.casefold()}_{suffix}"


def checkpoint_report(
    session: dict[str, object],
    media: list[dict[str, object]],
    checkpoint: str,
) -> dict[str, object]:
    mode = str(session.get(checkpoint_column(checkpoint, "mode")) or "")
    checkpoint_media = [
        item for item in media if str(item.get("checkpoint") or "") == checkpoint
    ]
    expected_slots = REQUIRED_EVIDENCE.get(mode, [])
    present_slots = {
        str(item.get("evidence_slot") or "")
        for item in checkpoint_media
        if not item.get("replaced_media_id")
    }
    missing_slots = [slot for slot in expected_slots if slot not in present_slots]
    blocked: list[dict[str, object]] = []
    for item in checkpoint_media:
        if item.get("freshness_status") == EvidenceFreshnessStatus.DATE_MISMATCH.value:
            blocked.append({
                "media_id": item.get("id"),
                "code": "DATE_MISMATCH",
                "message": "Data evidenza non coerente con il controllo corrente.",
            })
        if bool(item.get("reuse_detected")):
            blocked.append({
                "media_id": item.get("id"),
                "code": "REUSED_EVIDENCE",
                "message": "Evidenza già utilizzata in un controllo precedente.",
            })
    evidence_complete = bool(mode) and not missing_slots and not blocked
    completed_at = session.get(checkpoint_column(checkpoint, "completed_at"))
    return {
        "checkpoint": checkpoint,
        "mode": mode or None,
        "required_slots": expected_slots,
        "present_slots": sorted(present_slots),
        "missing_slots": missing_slots,
        "blocked": blocked,
        "evidence_complete": evidence_complete,
        "completed": bool(completed_at),
        "completed_at": completed_at,
        "started_at": session.get(checkpoint_column(checkpoint, "started_at")),
        "media_count": len(checkpoint_media),
    }


def parse_client_capture_time(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("Data di acquisizione non valida.") from exc
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(timezone.utc)


def classify_freshness(
    *,
    session: dict[str, object],
    received_at: datetime,
    received_operational_date: str,
    captured_at: datetime | None,
    captured_operational_date: str | None,
    capture_source: str,
) -> tuple[str, str | None]:
    expected_day = str(session.get("operational_date") or "")
    if not expected_day:
        return (
            EvidenceFreshnessStatus.NOT_VERIFIABLE.value,
            "Verifica data non disponibile per questo controllo storico.",
        )
    if received_operational_date != expected_day or (
        captured_operational_date is not None
        and captured_operational_date != expected_day
    ):
        return (
            EvidenceFreshnessStatus.DATE_MISMATCH.value,
            "Data evidenza non coerente con il controllo corrente.",
        )
    started_raw = (
        session.get("opened_at")
        or session.get("in_progress_at")
        or session.get("created_at")
    )
    try:
        started = datetime.fromisoformat(str(started_raw)).astimezone(timezone.utc)
    except (TypeError, ValueError):
        started = None
    capture_is_in_session = bool(
        capture_source == "camera"
        and captured_at is not None
        and started is not None
        and captured_at >= started - timedelta(minutes=5)
        and captured_at <= received_at + timedelta(minutes=5)
    )
    if capture_is_in_session:
        return EvidenceFreshnessStatus.VERIFIED_SESSION_CAPTURE.value, None
    return EvidenceFreshnessStatus.SAME_DAY_RECEIVED.value, None


def completion_evidence_report(
    session: dict[str, object],
    media: list[dict[str, object]],
) -> dict[str, object]:
    historical = session.get("evidence_policy_version") != EVIDENCE_POLICY_VERSION
    if historical:
        return {
            "policy_version": session.get("evidence_policy_version"),
            "historical": True,
            "historical_message": "Policy evidenze IN/OUT non disponibile per questo Journal storico.",
            "checkpoints": {},
            "missing": [],
            "blocked": [],
            "complete": True,
            "lifecycle_status": "LEGACY",
        }
    checkpoints = {
        checkpoint: checkpoint_report(session, media, checkpoint)
        for checkpoint in CHECKPOINTS
    }
    missing = [
        {
            "checkpoint": checkpoint,
            "mode": report["mode"],
            "missing_slots": report["missing_slots"],
        }
        for checkpoint, report in checkpoints.items()
        if not report["evidence_complete"]
    ]
    blocked = [
        {**item, "checkpoint": checkpoint}
        for checkpoint, report in checkpoints.items()
        for item in report["blocked"]
    ]
    complete = all(report["completed"] for report in checkpoints.values())
    check_in = checkpoints["CHECK_IN"]
    check_out = checkpoints["CHECK_OUT"]
    lifecycle = (
        "CHECK_IN_REQUIRED" if not check_in["completed"]
        else "CHECK_OUT_REQUIRED" if not check_out["completed"]
        else "READY_TO_CLOSE"
    )
    return {
        "policy_version": session.get("evidence_policy_version"),
        "historical": False,
        "required": REQUIRED_EVIDENCE,
        "checkpoints": checkpoints,
        "missing": missing,
        "blocked": blocked,
        "complete": complete,
        "lifecycle_status": lifecycle,
    }
