from app.plugins.workforce.domain.consecutivity import ConsecutivityPolicy


def evaluation(count: int | None, sufficient: bool, policy: ConsecutivityPolicy) -> tuple[str, str]:
    if not sufficient or count is None:
        return (
            "dati_insufficienti",
            "Storico lavorativo non sufficiente per calcolare la consecutivita.",
        )
    if count > policy.rest_required_threshold:
        return (
            "riposo_raccomandato",
            f"Riposo raccomandato: {count} giorni consecutivi secondo la policy aziendale.",
        )
    if count == policy.rest_required_threshold:
        return (
            "limite_raggiunto",
            f"Limite operativo raggiunto: {count} giorni consecutivi secondo la policy aziendale.",
        )
    if count >= policy.warning_threshold:
        return (
            "attenzione",
            f"{count} giorni consecutivi. Verificare la pianificazione del riposo.",
        )
    return (
        "regolare",
        f"Consecutivita regolare: {count} giorni secondo la policy aziendale.",
    )
