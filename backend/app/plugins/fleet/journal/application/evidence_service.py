from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.plugins.fleet.journal.domain.models import EvidenceFreshnessStatus


REQUIRED_EVIDENCE = {"photo": 1, "video": 1}
EVIDENCE_POLICY_VERSION = "1.0"
ALLOWED_CAPTURE_SOURCES = {"camera", "file"}


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
    historical = not session.get("evidence_policy_version")
    counts = {
        evidence_type: sum(
            str(item.get("evidence_type") or item.get("media_type"))
            == ("image" if evidence_type == "photo" else "video")
            or str(item.get("evidence_type")) == evidence_type
            for item in media
        )
        for evidence_type in REQUIRED_EVIDENCE
    }
    missing = [
        {"evidence_type": evidence_type, "required": required, "present": counts[evidence_type]}
        for evidence_type, required in REQUIRED_EVIDENCE.items()
        if counts[evidence_type] < required
    ]
    blocked = []
    for item in media:
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
    return {
        "policy_version": session.get("evidence_policy_version"),
        "historical": historical,
        "required": REQUIRED_EVIDENCE,
        "counts": counts,
        "missing": [] if historical else missing,
        "blocked": [] if historical else blocked,
        "complete": historical or (not missing and not blocked),
    }
