import hashlib
import hmac
import secrets
from datetime import date, datetime, timedelta, timezone

from app.auth.password_service import hash_password, verify_password
from app.core.config import SETTINGS
from app.plugins.workforce.application.driver_shift_credentials_service import (
    ACCESS_CODE_LENGTH,
    PIN_DIGITS,
    PIN_DOMAIN_PREFIX,
    access_code_fingerprint,
    normalize_access_code,
)
from app.plugins.workforce.domain.driver_shift_driver_session import (
    DriverShiftDriverView,
    DriverShiftPublicDay,
    DriverShiftPublicShift,
    DriverShiftPublicWeek,
    DriverShiftLoginInvalidError,
    DriverShiftLoginRateLimitedError,
    DriverShiftSessionInvalidError,
)
from app.plugins.workforce.infrastructure import (
    driver_shift_driver_session_repository as repository,
)


SESSION_COOKIE_NAME = "driver_shift_session"
SESSION_COOKIE_PATH = "/api/public/driver-shifts"
SESSION_COOKIE_SAMESITE = "strict"
SHORT_SESSION_HOURS = 8
REMEMBER_SESSION_DAYS = 30
RATE_WINDOW_MINUTES = 15
MAX_CODE_FAILURES = 5
MAX_IP_FAILURES = 20
DUMMY_PIN_HASH = hash_password(f"{PIN_DOMAIN_PREFIX}000000")
WEEKDAYS_IT = (
    "Lunedì", "Martedì", "Mercoledì", "Giovedì",
    "Venerdì", "Sabato", "Domenica",
)
MONTHS_IT = (
    "gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno",
    "luglio", "agosto", "settembre", "ottobre", "novembre", "dicembre",
)
SHIFT_LABELS = {
    "R": "Riposo",
    "RIPOSO": "Riposo",
    "REST": "Riposo",
    "FERIE": "Ferie",
    "HOLIDAY": "Ferie",
    "PERMESSO": "Permesso",
    "LEAVE": "Permesso",
    "MALATTIA": "Malattia",
    "SICK": "Malattia",
    "SICKNESS": "Malattia",
    "SCHEDULED": "Programmato",
}


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _key() -> bytes:
    return (SETTINGS.secret_key or "operations-engine-development-driver-shifts").encode(
        "utf-8"
    )


def _fingerprint(prefix: str, value: str) -> str:
    return hmac.new(_key(), f"{prefix}:{value}".encode("utf-8"), hashlib.sha256).hexdigest()


def portal_token_hash(token: str) -> str:
    return _sha256(token.strip())


def session_token_hash(token: str) -> str:
    return _sha256(token)


def client_ip_fingerprint(client_ip: str) -> str:
    return _fingerprint("driver-shift-ip-v1", client_ip or "unknown")


def _expiry(portal_expires_at: str, remember_device: bool) -> datetime:
    now = datetime.now(timezone.utc)
    duration = timedelta(days=REMEMBER_SESSION_DAYS) if remember_device else timedelta(
        hours=SHORT_SESSION_HOURS
    )
    portal_expiry = datetime.fromisoformat(portal_expires_at.replace("Z", "+00:00"))
    if portal_expiry.tzinfo is None:
        portal_expiry = portal_expiry.replace(tzinfo=timezone.utc)
    return min(now + duration, portal_expiry)


def cookie_options(*, remember_device: bool, expires_at: datetime) -> dict:
    return {
        "httponly": True,
        "secure": SETTINGS.production,
        "samesite": SESSION_COOKIE_SAMESITE,
        "path": SESSION_COOKIE_PATH,
        "expires": expires_at if remember_device else None,
    }


def login(
    *,
    portal_token: str,
    access_code: str,
    pin: str,
    remember_device: bool,
    client_ip: str,
) -> tuple[DriverShiftDriverView, str, datetime]:
    portal = repository.portal_context(portal_token_hash(portal_token))
    if portal is None:
        raise DriverShiftLoginInvalidError("Dati di accesso non validi.")

    normalized_code = normalize_access_code(access_code)
    code_fingerprint = access_code_fingerprint(normalized_code)
    ip_fingerprint = client_ip_fingerprint(client_ip)
    code_failures, ip_failures = repository.failed_attempt_counts(
        int(portal["portal_id"]), code_fingerprint, ip_fingerprint,
        window_minutes=RATE_WINDOW_MINUTES,
    )
    if code_failures >= MAX_CODE_FAILURES or ip_failures >= MAX_IP_FAILURES:
        raise DriverShiftLoginRateLimitedError("Dati di accesso non validi.")

    valid_shape = (
        len(normalized_code) == ACCESS_CODE_LENGTH
        and len(pin) == PIN_DIGITS
        and pin.isdigit()
    )
    credential = None
    if valid_shape:
        credential = repository.credential_for_portal(
            str(portal["organization_id"]), int(portal["distribution_id"]),
            code_fingerprint,
        )
    pin_hash = str(credential["pin_hash"]) if credential else DUMMY_PIN_HASH
    pin_matches = valid_shape and verify_password(f"{PIN_DOMAIN_PREFIX}{pin}", pin_hash)
    valid = bool(
        credential
        and credential["credential_status"] == "ACTIVE"
        and credential["access_revoked_at"] is None
        and pin_matches
    )
    repository.record_login_attempt(
        organization_id=str(portal["organization_id"]),
        portal_id=int(portal["portal_id"]),
        access_code_fingerprint=code_fingerprint,
        ip_fingerprint=ip_fingerprint,
        succeeded=valid,
    )
    if not valid or credential is None:
        raise DriverShiftLoginInvalidError("Dati di accesso non validi.")

    expires_at = _expiry(str(portal["portal_expires_at"]), remember_device)
    raw_token = secrets.token_urlsafe(48)
    repository.create_session(
        session_token_hash=session_token_hash(raw_token),
        organization_id=str(portal["organization_id"]),
        workforce_member_id=int(credential["workforce_member_id"]),
        distribution_id=int(portal["distribution_id"]),
        portal_id=int(portal["portal_id"]),
        portal_generation=int(portal["portal_generation"]),
        credential_generation=int(credential["credential_generation"]),
        expires_at=expires_at.isoformat(),
        remember_device=remember_device,
    )
    row = repository.session_view(session_token_hash(raw_token))
    assert row is not None
    return _view(row), raw_token, expires_at


def _view(row: dict) -> DriverShiftDriverView:
    return DriverShiftDriverView(
        driver_name=str(row["display_name"]),
        period_start=str(row["period_start"]),
        period_end=str(row["period_end"]),
        access_status=str(row["access_status"]),
    )


def current_session(raw_token: str | None) -> DriverShiftDriverView:
    if not raw_token:
        raise DriverShiftSessionInvalidError("Sessione driver non valida.")
    row = repository.session_view(session_token_hash(raw_token))
    if row is None:
        raise DriverShiftSessionInvalidError("Sessione driver non valida.")
    return _view(row)


def _shift(row: dict) -> DriverShiftPublicShift:
    raw = str(row.get("shift_code") or "").strip()
    semantic_value = raw or str(row.get("status_code") or "").strip()
    label = SHIFT_LABELS.get(
        semantic_value.upper(), semantic_value or "Turno non disponibile",
    )
    return DriverShiftPublicShift(
        raw_shift_code=raw or None,
        display_label=label,
        start_time=row.get("start_time"),
        end_time=row.get("end_time"),
        status=str(row.get("status_code")) if row.get("status_code") is not None else None,
        availability=bool(row["availability"]) if row.get("availability") is not None else None,
        station=row.get("station"),
    )


def build_week_days(
    period_start: str,
    period_end: str,
    published_rows: list[dict],
) -> list[DriverShiftPublicDay]:
    start = date.fromisoformat(period_start)
    end = date.fromisoformat(period_end)
    if end < start:
        raise DriverShiftSessionInvalidError("Periodo turni non valido.")
    grouped: dict[str, list[dict]] = {}
    for row in published_rows:
        grouped.setdefault(str(row["operational_date"]), []).append(row)
    days: list[DriverShiftPublicDay] = []
    current = start
    while current <= end:
        operational_date = current.isoformat()
        rows = grouped.get(operational_date, [])
        shifts = [_shift(row) for row in rows]
        if not shifts:
            shifts = [DriverShiftPublicShift(display_label="Turno non disponibile")]
        weekday = WEEKDAYS_IT[current.weekday()]
        days.append(DriverShiftPublicDay(
            operational_date=operational_date,
            weekday_label=weekday,
            date_label=f"{weekday} {current.day} {MONTHS_IT[current.month - 1]}",
            missing=not rows,
            shifts=shifts,
        ))
        current += timedelta(days=1)
    return days


def _week(row: dict) -> DriverShiftPublicWeek:
    acknowledged_at = row.get("acknowledged_at")
    return DriverShiftPublicWeek(
        driver_name=str(row["display_name"]),
        period_start=str(row["period_start"]),
        period_end=str(row["period_end"]),
        days=build_week_days(
            str(row["period_start"]), str(row["period_end"]),
            list(row["published_rows"]),
        ),
        acknowledged=acknowledged_at is not None,
        acknowledged_at=acknowledged_at,
    )


def current_shifts(raw_token: str | None) -> DriverShiftPublicWeek:
    if not raw_token:
        raise DriverShiftSessionInvalidError("Sessione driver non valida.")
    row = repository.session_week_data(session_token_hash(raw_token))
    if row is None:
        raise DriverShiftSessionInvalidError("Sessione driver non valida.")
    return _week(row)


def acknowledge_shifts(raw_token: str | None) -> DriverShiftPublicWeek:
    if not raw_token:
        raise DriverShiftSessionInvalidError("Sessione driver non valida.")
    row = repository.session_week_data(
        session_token_hash(raw_token), acknowledge=True,
    )
    if row is None:
        raise DriverShiftSessionInvalidError("Sessione driver non valida.")
    return _week(row)


def logout(raw_token: str | None) -> None:
    if raw_token:
        repository.revoke_session(session_token_hash(raw_token))
