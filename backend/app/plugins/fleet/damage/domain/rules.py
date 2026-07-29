STATUSES = (
    "nuova",
    "in_valutazione",
    "preventivo_richiesto",
    "preventivo_ricevuto",
    "riparazione_programmata",
    "in_riparazione",
    "chiusa",
    "annullata",
)
SEVERITIES = ("bassa", "media", "alta", "critica")
VEHICLE_STATUSES = (
    "disponibile",
    "disponibile_con_limitazioni",
    "fermo",
    "in_officina",
)
ORIGINS = ("journal", "vehicle_library", "manual")

FORWARD = {
    "nuova": "in_valutazione",
    "in_valutazione": "preventivo_richiesto",
    "preventivo_richiesto": "preventivo_ricevuto",
    "preventivo_ricevuto": "riparazione_programmata",
    "riparazione_programmata": "in_riparazione",
    "in_riparazione": "chiusa",
}


def validate_transition(previous: str, current: str, note: str | None) -> None:
    if current not in STATUSES:
        raise ValueError("Stato pratica non valido.")
    if previous == current:
        raise ValueError("La pratica è già nello stato richiesto.")
    if current == "annullata":
        if not note:
            raise ValueError("L'annullamento richiede una nota.")
        return
    if previous == "chiusa":
        if current != "in_valutazione" or not note:
            raise ValueError("La riapertura richiede una nota e lo stato in valutazione.")
        return
    if previous == "annullata":
        raise ValueError("Una pratica annullata non può cambiare stato.")
    if FORWARD.get(previous) == current:
        if not note:
            raise ValueError("Ogni cambio di stato richiede una nota.")
        return
    if current in STATUSES and note:
        return
    raise ValueError("Transizione non consentita senza motivazione.")


def fleet_availability(vehicle_status: str) -> str:
    return {
        "disponibile": "available",
        "disponibile_con_limitazioni": "available",
        "fermo": "unavailable",
        "in_officina": "maintenance",
    }[vehicle_status]
