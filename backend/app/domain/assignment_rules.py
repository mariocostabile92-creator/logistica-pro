import re

from app.domain.normalized_models import NormalizedFleetRow
from app.utils.text_normalizer import normalize_text


OPERATIONAL_VEHICLE_STATUSES = {
    "operativo",
    "operativa",
    "disponibile",
    "disponibilita",
    "available",
    "active",
    "attivo",
    "attiva",
    "ok",
}
RESERVE_VEHICLE_STATUSES = {"riserva", "reserve", "spare"}


def is_valid_plate(plate: str | None) -> bool:
    if not plate or not re.fullmatch(r"[A-Z0-9]{5,8}", plate):
        return False
    return any(char.isalpha() for char in plate) and any(char.isdigit() for char in plate)


def station_key(station: str | None) -> str:
    return normalize_text(station).replace(" ", "")


def vehicle_operational_state(
    vehicle: NormalizedFleetRow,
    blocked_statuses: list[str],
    unrecognized_status_is_blocking: bool,
) -> str:
    if not is_valid_plate(vehicle.vehicle_plate):
        return "invalid"

    status = normalize_text(vehicle.status)
    workshop = normalize_text(vehicle.workshop)
    notes = normalize_text(vehicle.notes)
    blocked_terms = {normalize_text(item) for item in blocked_statuses}
    if any(term and (term in status or term in workshop) for term in blocked_terms):
        return "blocked"
    if status in RESERVE_VEHICLE_STATUSES or "riserva" in notes or "reserve" in notes:
        return "reserve"
    if status in OPERATIONAL_VEHICLE_STATUSES:
        return "operational"
    return "blocked" if unrecognized_status_is_blocking else "operational"
