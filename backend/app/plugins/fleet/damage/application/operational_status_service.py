from app.plugins.fleet.application.asset_service import get_asset, observe_availability
from app.plugins.fleet.damage.infrastructure import repository


OPERATIONAL_STATES = (
    "disponibile",
    "disponibile_con_limitazioni",
    "indisponibile",
    "in_manutenzione",
    "in_officina",
)
PRIORITY = {
    "disponibile": 0,
    "disponibile_con_limitazioni": 1,
    "indisponibile": 2,
    "in_manutenzione": 3,
    "in_officina": 4,
}
LEGACY = {
    "available": "disponibile",
    "reserve": "disponibile_con_limitazioni",
    "unavailable": "indisponibile",
    "maintenance": "in_manutenzione",
    "fermo": "indisponibile",
}
AUTOMATIC_SEVERITY = {"alta": "indisponibile", "critica": "indisponibile"}
AUTOMATIC_CASE_STATUS = {
    "riparazione_programmata": "in_manutenzione",
    "in_riparazione": "in_officina",
}
BLOCKING_STATES = {"indisponibile", "in_manutenzione", "in_officina"}


def normalize(value: str) -> str:
    normalized = LEGACY.get(value, value)
    if normalized not in OPERATIONAL_STATES:
        raise ValueError("Stato operativo del mezzo non valido.")
    return normalized


def suggested_for_severity(severity: str) -> str:
    return {
        "bassa": "disponibile",
        "media": "disponibile_con_limitazioni",
        "alta": "indisponibile",
        "critica": "indisponibile",
    }[severity]


def _most_restrictive(states: list[str], fallback: str) -> str:
    normalized = [normalize(value) for value in states]
    return max(normalized or [normalize(fallback)], key=lambda value: PRIORITY[value])


def requires_reason(previous: str, current: str, has_open_case: bool) -> bool:
    previous = normalize(previous)
    current = normalize(current)
    return current == "disponibile" and (
        has_open_case or previous in BLOCKING_STATES
    )


def apply(
    *,
    case_id: int,
    requested: str,
    actor: str,
    reason: str,
    origin: str,
) -> str:
    case = repository.get_case(case_id)
    if not case:
        raise ValueError("Pratica danno non trovata.")
    asset = get_asset(int(case["vehicle_id"]))
    previous = normalize(asset.availability)
    requested = normalize(requested)
    other_states = repository.open_case_operational_states(
        int(case["vehicle_id"]), excluding_case_id=case_id,
    )
    effective = _most_restrictive([requested, *other_states], previous)
    if requires_reason(previous, requested, bool(other_states) or case["status"] not in {"chiusa", "annullata"}):
        if not reason.strip():
            raise ValueError("La modifica richiede una motivazione.")
    repository.record_operational_status(
        case_id, previous, effective, reason, actor, origin,
    )
    if effective != previous:
        observe_availability(
            int(case["vehicle_id"]),
            effective,
            f"{origin}: {reason}",
            actor,
        )
    return effective


def automatic_for_severity(case_id: int, severity: str, actor: str) -> tuple[str | None, str | None]:
    requested = AUTOMATIC_SEVERITY.get(severity)
    if not requested:
        warning = (
            "Valutare eventuali limitazioni operative del mezzo."
            if severity == "media" else None
        )
        return None, warning
    message = (
        "Mezzo bloccato automaticamente per danno critico."
        if severity == "critica"
        else "Il mezzo è stato impostato come Indisponibile per danno di gravità alta."
    )
    return apply(
        case_id=case_id, requested=requested, actor=actor,
        reason=message, origin=f"Pratica {repository.get_case(case_id)['case_number']}",
    ), message


def automatic_for_case_status(case_id: int, status: str, actor: str, note: str) -> str | None:
    requested = AUTOMATIC_CASE_STATUS.get(status)
    if not requested:
        return None
    return apply(
        case_id=case_id, requested=requested, actor=actor, reason=note,
        origin=f"Pratica {repository.get_case(case_id)['case_number']}",
    )
