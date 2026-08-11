import hashlib
import hmac
import secrets
from concurrent.futures import ThreadPoolExecutor

from app.auth.password_service import hash_password, verify_password
from app.core.config import SETTINGS
from app.plugins.workforce.domain.driver_shift_credentials import (
    DriverShiftCredentialMutationResult,
    DriverShiftCredentialPrepareResult,
    DriverShiftCredentialReadModel,
    DriverShiftCredentialRecipient,
    DriverShiftCredentialResetResult,
    DriverShiftCredentialSummary,
    DriverShiftInitialCredential,
)
from app.plugins.workforce.infrastructure import driver_shift_credentials_repository as repository


ACCESS_CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
ACCESS_CODE_LENGTH = 8
PIN_DIGITS = 6
PIN_DOMAIN_PREFIX = "driver-shift-pin:v1:"


def normalize_access_code(value: str) -> str:
    return "".join(character for character in value.strip().upper() if character not in " -")


def _access_code_hash(value: str) -> str:
    key = (SETTINGS.secret_key or "operations-engine-development-driver-shifts").encode("utf-8")
    return hmac.new(key, normalize_access_code(value).encode("utf-8"), hashlib.sha256).hexdigest()


def access_code_fingerprint(value: str) -> str:
    """Return the deterministic, non-reversible credential lookup value."""
    return _access_code_hash(value)


def _new_access_code() -> str:
    return "".join(secrets.choice(ACCESS_CODE_ALPHABET) for _ in range(ACCESS_CODE_LENGTH))


def _new_pin(excluded: set[str] | None = None) -> str:
    excluded = excluded or set()
    while True:
        pin = f"{secrets.randbelow(10 ** PIN_DIGITS):0{PIN_DIGITS}d}"
        if pin not in excluded:
            return pin


def _hash_pin(pin: str) -> str:
    return hash_password(f"{PIN_DOMAIN_PREFIX}{pin}")


def _read_model(distribution_id: int, rows: list[dict], *, newly_created: int = 0,
                initial_credentials: list[DriverShiftInitialCredential] | None = None,
                errors: int = 0) -> DriverShiftCredentialReadModel | DriverShiftCredentialPrepareResult:
    recipients = [
        DriverShiftCredentialRecipient(
            workforce_member_id=int(row["workforce_member_id"]),
            display_name=str(row["display_name"]),
            credential_status=row.get("credential_status"),
        )
        for row in rows
    ]
    ready = sum(item.credential_status == "ACTIVE" for item in recipients)
    revoked = sum(item.credential_status == "REVOKED" for item in recipients)
    reset_required = sum(item.credential_status == "RESET_REQUIRED" for item in recipients)
    missing = sum(item.credential_status is None for item in recipients)
    summary = DriverShiftCredentialSummary(
        recipients_total=len(recipients),
        credentials_ready=ready,
        already_existing=max(0, ready - newly_created),
        newly_created=newly_created,
        revoked=revoked,
        reset_required=reset_required,
        missing=missing,
        errors=errors,
    )
    values = {
        "distribution_id": distribution_id,
        "summary": summary,
        "recipients": recipients,
    }
    if initial_credentials is None:
        return DriverShiftCredentialReadModel(**values)
    return DriverShiftCredentialPrepareResult(
        **values, initial_credentials=initial_credentials,
    )


def credential_status(organization_id: str,
                      distribution_id: int) -> DriverShiftCredentialReadModel:
    rows = repository.distribution_recipients(organization_id, distribution_id)
    return _read_model(distribution_id, rows)


def prepare_credentials(organization_id: str, distribution_id: int,
                        actor: str) -> DriverShiftCredentialPrepareResult:
    rows = repository.distribution_recipients(
        organization_id, distribution_id, require_current=True,
    )
    missing = [row for row in rows if row.get("credential_status") is None]
    occupied_hashes = repository.access_code_hashes()
    used_pins: set[str] = set()
    generated: list[tuple[dict, str, str, str]] = []
    initial: list[DriverShiftInitialCredential] = []
    for row in missing:
        while True:
            access_code = _new_access_code()
            access_hash = _access_code_hash(access_code)
            if access_hash not in occupied_hashes:
                occupied_hashes.add(access_hash)
                break
        pin = _new_pin(used_pins)
        used_pins.add(pin)
        generated.append((row, access_code, access_hash, pin))
        initial.append(DriverShiftInitialCredential(
            display_name=str(row["display_name"]),
            access_code=access_code,
            initial_pin=pin,
        ))
    workers = min(8, len(generated))
    if workers:
        with ThreadPoolExecutor(max_workers=workers) as executor:
            pin_hashes = list(executor.map(_hash_pin, (item[3] for item in generated)))
    else:
        pin_hashes = []
    inserts = [
        {
            "workforce_member_id": int(row["workforce_member_id"]),
            "access_code_hash": access_hash,
            "pin_hash": pin_hash,
        }
        for (row, _access_code, access_hash, _pin), pin_hash in zip(
            generated, pin_hashes, strict=True,
        )
    ]
    repository.create_credentials(
        organization_id, distribution_id, inserts, actor,
    )
    refreshed = repository.distribution_recipients(organization_id, distribution_id)
    return _read_model(
        distribution_id, refreshed, newly_created=len(initial),
        initial_credentials=initial,
    )


def reset_credential(organization_id: str, workforce_member_id: int,
                     actor: str) -> DriverShiftCredentialResetResult:
    pin = _new_pin()
    row = repository.reset_credential(
        organization_id, workforce_member_id, _hash_pin(pin), actor,
    )
    return DriverShiftCredentialResetResult(
        workforce_member_id=workforce_member_id,
        display_name=str(row["display_name"]),
        credential_status=str(row["credential_status"]),
        generation=int(row["generation"]),
        initial_pin=pin,
    )


def revoke_credential(organization_id: str, workforce_member_id: int,
                      actor: str) -> DriverShiftCredentialMutationResult:
    row = repository.revoke_credential(
        organization_id, workforce_member_id, actor,
    )
    return DriverShiftCredentialMutationResult(
        workforce_member_id=workforce_member_id,
        display_name=str(row["display_name"]),
        credential_status=str(row["credential_status"]),
        generation=int(row["generation"]),
    )


def verify_credential(organization_id: str, access_code: str, pin: str) -> bool:
    normalized = normalize_access_code(access_code)
    if len(normalized) != ACCESS_CODE_LENGTH or not pin.isdigit() or len(pin) != PIN_DIGITS:
        return False
    row = repository.credential_by_access_code(
        organization_id, _access_code_hash(normalized),
    )
    if row is None or row["credential_status"] != "ACTIVE":
        return False
    return verify_password(f"{PIN_DOMAIN_PREFIX}{pin}", str(row["pin_hash"]))
