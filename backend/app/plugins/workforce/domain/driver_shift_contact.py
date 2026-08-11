import re
from dataclasses import dataclass

from app.plugins.workforce.domain.driver_shift_distribution import (
    DriverShiftContactChannel,
    DriverShiftContactReadiness,
)


EMAIL_PATTERN = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


@dataclass(frozen=True)
class NormalizedDriverContact:
    phone: str | None
    email: str | None
    readiness: DriverShiftContactReadiness
    available_channels: tuple[DriverShiftContactChannel, ...]
    preferred_channel: DriverShiftContactChannel | None


def normalize_phone(value: str | None) -> str | None:
    raw = (value or "").strip()
    if not raw:
        return None
    compact = re.sub(r"[\s()./-]", "", raw)
    if compact.startswith("00"):
        compact = f"+{compact[2:]}"
    elif compact.isdigit() and len(compact) == 10 and compact.startswith("3"):
        compact = f"+39{compact}"
    if not compact.startswith("+") or not compact[1:].isdigit():
        return None
    digits = compact[1:]
    return compact if 8 <= len(digits) <= 15 else None


def normalize_email(value: str | None) -> str | None:
    normalized = (value or "").strip().casefold()
    if not normalized or len(normalized) > 254 or not EMAIL_PATTERN.fullmatch(normalized):
        return None
    return normalized


def contact_readiness(phone: str | None, email: str | None) -> NormalizedDriverContact:
    has_original = bool((phone or "").strip() or (email or "").strip())
    normalized_phone = normalize_phone(phone)
    normalized_email = normalize_email(email)
    channels = tuple(
        channel for channel, present in (
            (DriverShiftContactChannel.PHONE, normalized_phone),
            (DriverShiftContactChannel.EMAIL, normalized_email),
        ) if present
    )
    readiness = (
        DriverShiftContactReadiness.READY if channels
        else DriverShiftContactReadiness.INVALID_CONTACT if has_original
        else DriverShiftContactReadiness.MISSING_CONTACT
    )
    preferred = (
        DriverShiftContactChannel.PHONE if normalized_phone
        else DriverShiftContactChannel.EMAIL if normalized_email
        else None
    )
    return NormalizedDriverContact(
        phone=normalized_phone,
        email=normalized_email,
        readiness=readiness,
        available_channels=channels,
        preferred_channel=preferred,
    )
