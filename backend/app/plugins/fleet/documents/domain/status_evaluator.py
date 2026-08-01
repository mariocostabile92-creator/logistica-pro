from datetime import date, datetime
from zoneinfo import ZoneInfo


EXPIRING_DAYS = 30
STATUS_COMPLETE = "completo"
STATUS_MISSING_FILE = "file_mancante"
STATUS_EXPIRING = "in_scadenza"
STATUS_EXPIRED = "scaduto"
STATUS_NO_EXPIRY = "senza_scadenza"
STATUS_ARCHIVED = "archiviato"
DOCUMENT_STATUSES = {
    STATUS_COMPLETE, STATUS_MISSING_FILE, STATUS_EXPIRING,
    STATUS_EXPIRED, STATUS_NO_EXPIRY, STATUS_ARCHIVED,
}


def organization_today(timezone_name: str | None) -> date:
    try:
        return datetime.now(ZoneInfo(timezone_name or "Europe/Rome")).date()
    except (KeyError, ValueError):
        return datetime.now(ZoneInfo("Europe/Rome")).date()


def evaluate_document(item: dict, timezone_name: str | None, today: date | None = None) -> dict:
    current = today or organization_today(timezone_name)
    has_file = bool(item.get("file_reference") or int(item.get("attachment_count") or 0))
    due = date.fromisoformat(str(item["expires_at"])[:10]) if item.get("expires_at") else None
    days = (due - current).days if due else None
    if item.get("archived_at"):
        status, reason = STATUS_ARCHIVED, "Documento archiviato."
    elif not has_file:
        status, reason = STATUS_MISSING_FILE, "Nessun allegato valido presente nell'Attachment Engine."
    elif days is not None and days < 0:
        status, reason = STATUS_EXPIRED, f"Scaduto da {abs(days)} giorni."
    elif days is not None and days <= EXPIRING_DAYS:
        status, reason = STATUS_EXPIRING, f"Scadenza tra {days} giorni."
    elif due is None:
        status, reason = STATUS_NO_EXPIRY, "Documento completo senza data di scadenza."
    else:
        status, reason = STATUS_COMPLETE, f"Documento valido; scadenza tra {days} giorni."
    return {**item, "status": status, "has_file": has_file, "days_to_expiry": days,
            "status_reason": reason, "expiring_threshold_days": EXPIRING_DAYS}
