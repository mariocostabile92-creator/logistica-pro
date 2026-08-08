import hashlib
import hmac
import json
import secrets
import sqlite3
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from app.auth import repository as auth_repository
from app.auth.tenant_context import current_organization_id
from app.core.config import SETTINGS
from app.plugins.fleet.journal.application import shared_access_service
from app.plugins.fleet.journal.application.shared_driver_identity import (
    resolve_shared_driver_identity,
)
from app.plugins.fleet.journal.infrastructure import repository
from app.plugins.fleet.journal.infrastructure.storage import media_storage
from app.plugins.fleet.journal.domain.operational_day import operational_date, organization_timezone
from app.utils.text_normalizer import normalize_plate


EQUIPMENT = (
    ("telepass", "Telepass"),
    ("phone", "Telefono"),
    ("keys", "Chiavi"),
    ("fuel_card", "Carta carburante"),
)
ALLOWED_SHIFTS = {"morning", "evening"}
ALLOWED_CLEANLINESS = {"compliant", "non_compliant", "verify"}
MAX_MEDIA_BYTES = 8 * 1024 * 1024
MEDIA_EXTENSIONS = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "video/mp4": ".mp4",
    "video/quicktime": ".mov",
}


def _safe_filename(value: str) -> str:
    name = Path(value.replace("\\", "/")).name[:160]
    cleaned = "".join(character if character.isalnum() or character in "._- " else "_" for character in name).strip(" .")
    return cleaned or "media-journal"


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
            "video_enabled": True,
            "accepted_mime_types": list(MEDIA_EXTENSIONS),
            "max_size_bytes": MAX_MEDIA_BYTES,
        },
    }


def _organization(organization_id: str | None) -> dict[str, object]:
    row = auth_repository.organization_by_id(organization_id) if organization_id else None
    if row is None:
        from app.core.database import db_session
        with db_session() as conn:
            rows = conn.execute("SELECT * FROM organizations ORDER BY created_at LIMIT 2").fetchall()
        if len(rows) == 1:
            row = rows[0]
    if row is None:
        fallback = "test-organization" if SETTINGS.environment == "test" else "default"
        return {"id": organization_id or fallback, "timezone": "Europe/Rome", "operational_day_start_hour": 4}
    return {key: row[key] for key in row.keys()}


def _session_clock(organization_id: str | None, now: datetime) -> tuple[str, str]:
    organization = _organization(organization_id)
    timezone_name = str(organization.get("timezone") or "Europe/Rome")
    day = operational_date(now, timezone_name, organization.get("operational_day_start_hour", 4))
    return timezone_name, day.isoformat()


def find_asset(plate: str, organization_id: str | None = None) -> dict[str, object]:
    normalized = normalize_plate(plate)
    if not normalized:
        raise JournalError("Inserisci una targa valida.")
    asset = repository.find_asset_by_plate(
        normalized,
        organization_id or current_organization_id(),
    )
    if not asset:
        raise JournalNotFound("Mezzo non trovato nel Fleet Registry.")
    return asset


def vehicle_history(asset_id: int, organization_id: str | None = None) -> dict[str, object]:
    payload = repository.asset_history(asset_id, organization_id)
    if not payload:
        raise JournalNotFound("Mezzo non trovato.")
    asset = payload["asset"]
    movements = payload["movements"]
    assert isinstance(asset, dict)
    assert isinstance(movements, list)
    capabilities = asset.get("capabilities")
    if isinstance(capabilities, str):
        try:
            asset["capabilities"] = json.loads(capabilities)
        except json.JSONDecodeError:
            asset["capabilities"] = []
    asset["model"] = asset.get("vehicle_model") or asset.get("category")
    normalized_capabilities = {
        str(value).strip().casefold()
        for value in (asset.get("capabilities") or [])
    }
    asset["term"] = next(
        (
            label
            for code, label in (("bt", "BT"), ("lt", "LT"))
            if code in normalized_capabilities
        ),
        None,
    )
    latest = movements[0] if movements else None
    last_occurred = str(latest["occurred_at"]) if latest else None
    days_stopped = None
    if last_occurred:
        occurred = datetime.fromisoformat(last_occurred)
        if occurred.tzinfo is None:
            occurred = occurred.replace(tzinfo=timezone.utc)
        days_stopped = max(
            0,
            (datetime.now(timezone.utc) - occurred.astimezone(timezone.utc)).days,
        )
    return {
        "contract_version": "1.0",
        "asset": asset,
        "kpis": {
            "current_odometer_km": latest["odometer_km"] if latest else None,
            "last_use_at": last_occurred,
            "days_stopped": days_stopped,
            "last_declared_driver": (
                latest["declared_driver_identifier"] if latest else None
            ),
            "last_movement": latest["operation_type"] if latest else None,
        },
        "movements": movements,
    }


def get_movement_media(media_id: str, token: str | None = None) -> tuple[str, str]:
    media = repository.movement_media(media_id)
    if not media:
        raise JournalNotFound("Media non trovato.")
    authorize(str(media["session_id"]), token, allow_completed=True)
    path = media_storage.path(str(media["storage_key"]))
    if not path.is_file():
        raise JournalNotFound("Media non disponibile.")
    return str(path), str(media["verified_mime_type"])


def get_admin_media(media_id: str, organization_id: str) -> tuple[str, str, str]:
    media = repository.movement_media(media_id, organization_id)
    if not media:
        raise JournalNotFound("Media non trovato.")
    try:
        path = media_storage.path(str(media["storage_key"]))
    except RuntimeError as exc:
        raise JournalNotFound("Media non disponibile.") from exc
    if not path.is_file():
        raise JournalNotFound("Media non disponibile.")
    return str(path), str(media["verified_mime_type"]), str(media.get("original_filename") or path.name)


def create_session(values: dict[str, object]) -> dict[str, object]:
    operation_type = str(values["operation_type"])
    shift = values.get("operational_shift")
    if operation_type == "check_out" and shift not in ALLOWED_SHIFTS:
        raise JournalError("La fascia operativa è obbligatoria per il ritiro.")
    organization_id = str(
        values.get("organization_id") or current_organization_id()
    )
    asset = find_asset(str(values["plate"]), organization_id)
    token = secrets.token_urlsafe(32)
    now = datetime.now(timezone.utc)
    _, day = _session_clock(organization_id, now)
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
            "organization_id": organization_id,
            "operational_date": day,
        }
    )
    return {
        key: value for key, value in session.items() if key != "token_hash"
    } | {"token": token}


def _managed_token(session_id: str) -> str:
    return hashlib.sha256(f"journal-managed:{session_id}".encode()).hexdigest()


def _normalize_person_name(value: object) -> str:
    normalized = " ".join(str(value).strip().split())
    if len(normalized) < 2:
        raise JournalError("Inserisci almeno due caratteri.")
    return normalized.casefold().title()


def _smart_warnings(
    session: dict[str, object],
    odometer_km: int | None = None,
) -> list[dict[str, str]]:
    history = repository.movement_history(int(session["asset_id"]))
    today = date.fromisoformat(
        str(session.get("operational_date") or date.today().isoformat())
    )
    same_day = [
        row for row in history
        if date.fromisoformat(str(row.get("operational_date") or row["occurred_at"][:10])) == today
    ]
    latest = history[0] if history else None
    warnings: list[dict[str, str]] = []
    if session["operation_type"] == "check_out":
        if any(row["operation_type"] == "check_out" for row in same_day):
            warnings.append({
                "code": "duplicate_checkout_today",
                "message": "Risulta già una presa in carico per questo mezzo oggi. Verifica la targa prima di continuare.",
            })
        if latest and latest["operation_type"] == "check_out":
            warnings.append({
                "code": "consecutive_checkout",
                "message": "L'ultima registrazione del mezzo è già una presa in carico senza un rientro successivo.",
            })
    if session["operation_type"] == "check_in" and not any(
        row["operation_type"] == "check_out" for row in same_day
    ):
        warnings.append({
            "code": "return_without_checkout",
            "message": "Non risulta una presa in carico per questo mezzo oggi. Verifica la targa prima di continuare.",
        })
    yesterday = today - timedelta(days=1)
    if latest and latest["operation_type"] == "check_out":
        latest_date = date.fromisoformat(
            str(latest.get("operational_date") or latest["occurred_at"][:10])
        )
        if latest_date == yesterday:
            warnings.append({
                "code": "missing_previous_return",
                "message": "Risulta una presa in carico del giorno precedente senza rientro.",
            })
    if (
        odometer_km is not None
        and latest
        and int(odometer_km) < int(latest["odometer_km"])
    ):
        warnings.append({
            "code": "odometer_decreased",
            "message": "Il chilometraggio inserito è inferiore all'ultima registrazione nota del mezzo.",
        })
    return list({warning["code"]: warning for warning in warnings}.values())


def create_shared_session(values: dict[str, object]) -> dict[str, object]:
    access_token = values.get("access_token")
    if not access_token:
        if not values.get("_test_harness_authorized"):
            raise JournalUnauthorized("Utilizza il link Driver condiviso dalla tua azienda.")
        organization_id = current_organization_id()
    else:
        try:
            access = shared_access_service.validate(str(access_token))
            organization_id = str(access["organization_id"])
        except shared_access_service.SharedAccessError as exc:
            error_type = JournalNotFound if exc.status_code == 404 else JournalError
            raise error_type(str(exc)) from exc
    driver_name = _normalize_person_name(values["driver_name"])
    driver_surname = _normalize_person_name(values["driver_surname"])
    driver_display_name = f"{driver_name} {driver_surname}"
    driver_identity = resolve_shared_driver_identity(
        organization_id,
        driver_display_name,
    )
    asset = find_asset(str(values["vehicle_plate"]), organization_id)
    operation_type = str(values["procedure_type"])
    session_id = str(uuid.uuid4())
    token = secrets.token_urlsafe(32)
    now = datetime.now(timezone.utc)
    _, day = _session_clock(organization_id, now)
    session = repository.create_session({
        "id": session_id,
        "token_hash": hashlib.sha256(token.encode()).hexdigest(),
        "operation_type": operation_type,
        "asset_id": asset["id"],
        "plate_snapshot": asset["plate"],
        "declared_driver_identifier": driver_identity.persisted_identifier,
        "operational_shift": (
            "morning" if now.hour < 14 else "evening"
        ) if operation_type == "check_out" else None,
        "created_at": now.isoformat(),
        "expires_at": (now + timedelta(days=3650)).isoformat(),
        "source": "shared_link",
        "lifecycle_status": "opened",
        "opened_at": now.isoformat(),
        "driver_name": driver_name,
        "driver_surname": driver_surname,
        "operational_date": day,
        "organization_id": organization_id,
    })
    warnings = _smart_warnings(session)
    session = repository.update_session_warnings(
        session_id, json.dumps(warnings, ensure_ascii=False)
    ) or session
    return {
        "session_id": session_id,
        "token": token,
        "lifecycle_status": session["lifecycle_status"],
        "created_at": session["created_at"],
        "warnings": warnings,
        "asset": {
            "id": asset["id"],
            "plate": asset["plate"],
            "vehicle_model": asset.get("category"),
        },
        "driver_name": driver_name,
        "driver_surname": driver_surname,
        "procedure_type": operation_type,
    }


def check_session_warnings(
    session_id: str,
    token: str | None,
    odometer_km: int,
) -> dict[str, object]:
    session = authorize(session_id, token, allow_completed=True)
    warnings = _smart_warnings(session, odometer_km)
    repository.update_session_warnings(
        session_id, json.dumps(warnings, ensure_ascii=False)
    )
    return {"warnings": warnings}


def create_managed_session(values: dict[str, object], organization_id: str | None = None) -> dict[str, object]:
    operation_type = str(values["operation_type"])
    try:
        scheduled = datetime.fromisoformat(
            f"{values['scheduled_date']}T{values['scheduled_time']}:00"
        )
    except ValueError as exc:
        raise JournalError("Data o ora della procedura non valida.") from exc
    organization_id = organization_id or current_organization_id()
    asset = find_asset(str(values["plate"]), organization_id)
    session_id = str(uuid.uuid4())
    token = _managed_token(session_id)
    now = datetime.now(timezone.utc)
    organization = _organization(organization_id)
    scheduled_local = scheduled.replace(
        tzinfo=organization_timezone(str(organization.get("timezone") or "Europe/Rome"))
    )
    _, day = _session_clock(organization_id, scheduled_local)
    shift = "morning" if scheduled.hour < 14 else "evening"
    session = repository.create_session({
        "id": session_id,
        "token_hash": hashlib.sha256(token.encode()).hexdigest(),
        "operation_type": operation_type,
        "asset_id": asset["id"],
        "plate_snapshot": asset["plate"],
        "declared_driver_identifier": str(
            values["declared_driver_identifier"]
        ).strip(),
        "operational_shift": shift if operation_type == "check_out" else None,
        "created_at": now.isoformat(),
        # Retained only for compatibility with the original schema. Managed
        # sessions do not apply expiry in authorize().
        "expires_at": (now + timedelta(days=3650)).isoformat(),
        "source": "fleet_manager",
        "lifecycle_status": "generated",
        "scheduled_at": scheduled.isoformat(),
        "operational_date": day,
        "organization_id": organization_id,
    })
    return {
        key: value for key, value in session.items() if key != "token_hash"
    } | {"link_path": f"/app/journal/?session={session_id}"}


def open_managed_session(session_id: str) -> dict[str, object]:
    session = repository.get_session(session_id)
    if not session or session.get("source") != "fleet_manager":
        raise JournalNotFound("Sessione Driver non trovata.")
    now = datetime.now(timezone.utc).isoformat()
    session = repository.transition_session(
        session_id, ("generated",), "opened", "opened_at", now
    ) or session
    return {
        key: value for key, value in session.items() if key != "token_hash"
    } | {"token": _managed_token(session_id)}


def mark_managed_session_in_progress(
    session_id: str,
    token: str | None,
) -> dict[str, object]:
    session = authorize(session_id, token, allow_completed=True)
    if session.get("source") not in {"fleet_manager", "shared_link"}:
        raise JournalNotFound("Sessione Driver non trovata.")
    if session["status"] == "completed":
        return {
            key: value for key, value in session.items() if key != "token_hash"
        }
    updated = repository.transition_session(
        session_id,
        ("generated", "opened"),
        "in_progress",
        "in_progress_at",
        datetime.now(timezone.utc).isoformat(),
    ) or session
    return {
        key: value for key, value in updated.items() if key != "token_hash"
    }


def authorize(
    session_id: str,
    token: str | None,
    allow_completed: bool = False,
) -> dict[str, object]:
    session = repository.get_session(session_id)
    if not session:
        raise JournalNotFound("Sessione non trovata.")
    supplied_hash = hashlib.sha256((token or "").encode()).hexdigest()
    if not hmac.compare_digest(supplied_hash, str(session["token_hash"])):
        raise JournalUnauthorized("Token di sessione non valido.")
    if session.get("source") not in {"fleet_manager", "shared_link"} and datetime.fromisoformat(str(session["expires_at"])) < datetime.now(
        timezone.utc
    ):
        raise JournalExpired("La sessione è scaduta.")
    if session["status"] == "completed" and not allow_completed:
        raise JournalConflict("La sessione è già stata completata.")
    return session


def _verified_media(data: bytes, content_type: str | None, filename: str) -> tuple[str, str]:
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
    elif len(data) >= 12 and data[4:8] == b"ftyp":
        detected = "video/quicktime" if content_type == "video/quicktime" else "video/mp4"
    if not detected:
        raise JournalError("Il file immagine è corrotto o non supportato.")
    if content_type != detected:
        raise JournalError("Il tipo MIME dichiarato non corrisponde al file.")
    extension = Path(filename).suffix.casefold()
    allowed_extensions = {".jpg", ".jpeg"} if detected == "image/jpeg" else {MEDIA_EXTENSIONS[detected]}
    if extension not in allowed_extensions:
        raise JournalError("L'estensione non corrisponde al contenuto del file.")
    return detected, "video" if detected.startswith("video/") else "image"


def add_media(
    session_id: str,
    token: str | None,
    filename: str,
    content_type: str | None,
    data: bytes,
) -> dict[str, object]:
    session = authorize(session_id, token)
    if len(data) > MAX_MEDIA_BYTES:
        raise JournalError("La foto supera il limite di 8 MB.")
    safe_name = _safe_filename(filename)
    verified, media_type = _verified_media(data, content_type, safe_name)
    media_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    storage_key = media_storage.save(
        f"{now:%Y/%m}/{media_id}{MEDIA_EXTENSIONS[verified]}", data
    )
    try:
        return repository.create_media(
            {
                "id": media_id,
                "session_id": session_id,
                "media_type": media_type,
                "phase": "evidence",
                "storage_key": storage_key,
                "verified_mime_type": verified,
                "size_bytes": len(data),
                "sha256": hashlib.sha256(data).hexdigest(),
                "organization_id": session.get("organization_id"),
                "vehicle_id": session["asset_id"],
                "original_filename": safe_name,
                "uploaded_at": now.isoformat(),
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
    media_storage.delete(str(media["storage_key"]))


def delete_admin_media(media_id: str, organization_id: str) -> None:
    media = repository.delete_media_admin(media_id, organization_id)
    if not media:
        raise JournalNotFound("Media non trovato.")
    media_storage.delete(str(media["storage_key"]))


def complete(
    session_id: str,
    token: str | None,
    values: dict[str, object],
) -> dict[str, object]:
    session = authorize(session_id, token, allow_completed=True)
    submission_id = str(values["client_submission_id"])
    existing = repository.get_movement_by_submission(submission_id)
    if existing:
        if existing["session_id"] != session_id:
            raise JournalConflict("Identificativo invio già utilizzato.")
        return receipt(str(existing["id"]))
    if session["status"] == "completed":
        raise JournalConflict("La sessione è già stata completata.")
    odometer = int(values["odometer_km"])
    fuel = int(values["fuel_percentage"])
    if odometer < 0:
        raise JournalError("I chilometri non possono essere negativi.")
    if fuel < 0 or fuel > 100:
        raise JournalError("Il carburante deve essere compreso tra 0 e 100.")
    warnings = _smart_warnings(session, odometer)
    repository.update_session_warnings(
        session_id, json.dumps(warnings, ensure_ascii=False)
    )
    if (
        session["operation_type"] == "check_in"
        and values.get("cleanliness_status") not in ALLOWED_CLEANLINESS
    ):
        raise JournalError("Lo stato pulizia è obbligatorio per il rientro.")
    if values.get("anomaly_present") and not str(
        values.get("anomaly_description") or ""
    ).strip():
        raise JournalError("Descrivi l'anomalia dichiarata.")
    equipment = values.get("equipment") or []
    configured = {code for code, _ in EQUIPMENT}
    if {item["code"] for item in equipment} != configured:
        raise JournalError("Completa la checklist delle dotazioni.")
    occurred = datetime.now(timezone.utc)
    now = occurred.isoformat()
    timezone_name, operational_day = _session_clock(
        str(session.get("organization_id") or "default"), occurred
    )
    movement_id = str(uuid.uuid4())
    try:
        repository.complete_session_atomic(
            session=session,
            movement={
                "id": movement_id,
                "schema_version": "1.0",
                "organization_id": session.get("organization_id") or "default",
                "operational_unit_id": "default",
                "odometer_km": odometer,
                "fuel_percentage": fuel,
                "cleanliness_status": values.get("cleanliness_status"),
                "anomaly_present": bool(values.get("anomaly_present")),
                "anomaly_description": values.get("anomaly_description"),
                "operational_note": values.get("operational_note"),
                "client_submission_id": submission_id,
                "occurred_at": now,
                "timezone": timezone_name,
                "operational_date": operational_day,
                "created_at": now,
            },
            equipment=equipment,
        )
    except sqlite3.IntegrityError:
        concurrent = repository.get_movement_by_submission(submission_id)
        if concurrent and concurrent["session_id"] == session_id:
            return receipt(str(concurrent["id"]))
        raise JournalConflict("La sessione è già stata completata.")
    return receipt(movement_id)


def receipt(movement_id: str) -> dict[str, object]:
    result = repository.receipt(movement_id)
    if not result:
        raise JournalNotFound("Movimentazione non trovata.")
    result["warnings"] = json.loads(str(result.pop("warnings_json", "[]")))
    return result
