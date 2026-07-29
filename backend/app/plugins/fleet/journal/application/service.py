import hashlib
import hmac
import secrets
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone

from app.plugins.fleet.journal.infrastructure import repository
from app.plugins.fleet.journal.infrastructure.storage import media_storage


EQUIPMENT = (
    ("telepass", "Telepass"),
    ("phone", "Telefono"),
    ("keys", "Chiavi"),
    ("fuel_card", "Carta carburante"),
)
ALLOWED_SHIFTS = {"morning", "evening"}
ALLOWED_CLEANLINESS = {"compliant", "non_compliant", "verify"}
MAX_MEDIA_BYTES = 8 * 1024 * 1024


class JournalError(ValueError):
    status_code = 422


class JournalNotFound(JournalError):
    status_code = 404


class JournalUnauthorized(JournalError):
    status_code = 403


class JournalConflict(JournalError):
    status_code = 409


class JournalExpired(JournalError):
    status_code = 410


def normalize_plate(value: str) -> str:
    return "".join(character for character in value.upper() if character.isalnum())


def configuration() -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "operation_types": ["check_out", "check_in"],
        "operational_shifts": [
            {"code": "morning", "label": "Mattino"},
            {"code": "evening", "label": "Sera"},
        ],
        "cleanliness_statuses": [
            {"code": "compliant", "label": "Conforme"},
            {"code": "non_compliant", "label": "Non conforme"},
            {"code": "verify", "label": "Da verificare"},
        ],
        "equipment": [
            {"code": code, "label": label} for code, label in EQUIPMENT
        ],
        "media": {
            "images_enabled": True,
            "video_enabled": False,
            "accepted_mime_types": ["image/jpeg", "image/png", "image/webp"],
            "max_size_bytes": MAX_MEDIA_BYTES,
        },
    }


def find_asset(plate: str) -> dict[str, object]:
    normalized = normalize_plate(plate)
    if not normalized:
        raise JournalError("Inserisci una targa valida.")
    asset = repository.find_asset_by_plate(normalized)
    if not asset:
        raise JournalNotFound("Mezzo non trovato nel Fleet Registry.")
    return asset


def create_session(values: dict[str, object]) -> dict[str, object]:
    operation_type = str(values["operation_type"])
    shift = values.get("operational_shift")
    if operation_type == "check_out" and shift not in ALLOWED_SHIFTS:
        raise JournalError("La fascia operativa è obbligatoria per il ritiro.")
    asset = find_asset(str(values["plate"]))
    token = secrets.token_urlsafe(32)
    now = datetime.now(timezone.utc)
    session_id = str(uuid.uuid4())
    session = repository.create_session(
        {
            "id": session_id,
            "token_hash": hashlib.sha256(token.encode()).hexdigest(),
            "operation_type": operation_type,
            "asset_id": asset["id"],
            "plate_snapshot": asset["plate"],
            "declared_driver_identifier": str(
                values["declared_driver_identifier"]
            ).strip(),
            "operational_shift": shift,
            "created_at": now.isoformat(),
            "expires_at": (now + timedelta(hours=4)).isoformat(),
        }
    )
    return {
        key: value for key, value in session.items() if key != "token_hash"
    } | {"token": token}


def authorize(session_id: str, token: str | None, allow_completed: bool = False):
    session = repository.get_session(session_id)
    if not session:
        raise JournalNotFound("Sessione non trovata.")
    supplied_hash = hashlib.sha256((token or "").encode()).hexdigest()
    if not hmac.compare_digest(supplied_hash, session["token_hash"]):
        raise JournalUnauthorized("Token di sessione non valido.")
    if datetime.fromisoformat(session["expires_at"]) < datetime.now(timezone.utc):
        raise JournalExpired("La sessione è scaduta.")
    if session["status"] == "completed" and not allow_completed:
        raise JournalConflict("La sessione è già stata completata.")
    return session


def _verified_image(data: bytes, content_type: str | None) -> str:
    detected = None
    if data.startswith(b"\xff\xd8\xff") and data.endswith(b"\xff\xd9"):
        detected = "image/jpeg"
    elif (
        len(data) >= 24
        and data.startswith(b"\x89PNG\r\n\x1a\n")
        and data[12:16] == b"IHDR"
    ):
        detected = "image/png"
    elif len(data) >= 16 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        detected = "image/webp"
    if not detected:
        raise JournalError("Il file immagine è corrotto o non supportato.")
    if content_type != detected:
        raise JournalError("Il tipo MIME dichiarato non corrisponde al file.")
    return detected


def add_media(
    session_id: str,
    token: str | None,
    filename: str,
    content_type: str | None,
    data: bytes,
) -> dict[str, object]:
    authorize(session_id, token)
    if len(data) > MAX_MEDIA_BYTES:
        raise JournalError("La foto supera il limite di 8 MB.")
    verified = _verified_image(data, content_type)
    media_id = str(uuid.uuid4())
    storage_key = media_storage.save(session_id, media_id, data)
    try:
        return repository.create_media(
            {
                "id": media_id,
                "session_id": session_id,
                "media_type": "image",
                "phase": "evidence",
                "storage_key": storage_key,
                "verified_mime_type": verified,
                "size_bytes": len(data),
                "sha256": hashlib.sha256(data).hexdigest(),
            }
        )
    except Exception:
        media_storage.delete(storage_key)
        raise


def delete_media(session_id: str, media_id: str, token: str | None) -> None:
    authorize(session_id, token)
    media = repository.get_session_media(session_id, media_id)
    if not media:
        raise JournalNotFound("Foto non trovata in questa sessione.")
    repository.delete_media(session_id, media_id)
    media_storage.delete(media["storage_key"])


def complete(
    session_id: str,
    token: str | None,
    values: dict[str, object],
) -> dict[str, object]:
    session = authorize(session_id, token, allow_completed=True)
    existing = repository.get_movement_by_submission(
        str(values["client_submission_id"])
    )
    if existing:
        if existing["session_id"] != session_id:
            raise JournalConflict("Identificativo invio già utilizzato.")
        return repository.receipt(existing["id"])
    if session["status"] == "completed":
        raise JournalConflict("La sessione è già stata completata.")
    odometer = int(values["odometer_km"])
    fuel = int(values["fuel_percentage"])
    if odometer < 0:
        raise JournalError("I chilometri non possono essere negativi.")
    if fuel < 0 or fuel > 100:
        raise JournalError("Il carburante deve essere compreso tra 0 e 100.")
    if session["operation_type"] == "check_in":
        if values.get("cleanliness_status") not in ALLOWED_CLEANLINESS:
            raise JournalError("Lo stato pulizia è obbligatorio per il rientro.")
    if values.get("anomaly_present") and not str(
        values.get("anomaly_description") or ""
    ).strip():
        raise JournalError("Descrivi l'anomalia dichiarata.")
    equipment = values.get("equipment") or []
    configured = {code for code, _ in EQUIPMENT}
    if {item["code"] for item in equipment} != configured:
        raise JournalError("Completa la checklist delle dotazioni.")
    now = datetime.now(timezone.utc).isoformat()
    movement_id = str(uuid.uuid4())
    try:
        repository.complete_session_atomic(
            session=session,
            movement={
            "id": movement_id,
            "schema_version": "1.0",
            "organization_id": "default",
            "operational_unit_id": "default",
            "odometer_km": odometer,
            "fuel_percentage": fuel,
            "cleanliness_status": values.get("cleanliness_status"),
            "anomaly_present": bool(values.get("anomaly_present")),
            "anomaly_description": values.get("anomaly_description"),
            "operational_note": values.get("operational_note"),
            "client_submission_id": str(values["client_submission_id"]),
            "occurred_at": now,
            "timezone": str(values.get("timezone") or "Europe/Rome"),
            "created_at": now,
            },
            equipment=equipment,
        )
    except sqlite3.IntegrityError:
        concurrent = repository.get_movement_by_submission(
            str(values["client_submission_id"])
        )
        if concurrent and concurrent["session_id"] == session_id:
            return repository.receipt(concurrent["id"])
        raise JournalConflict("La sessione è già stata completata.")
    return repository.receipt(movement_id)


def receipt(movement_id: str) -> dict[str, object]:
    result = repository.receipt(movement_id)
    if not result:
        raise JournalNotFound("Movimentazione non trovata.")
    return result
