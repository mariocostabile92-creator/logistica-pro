def planning_contract(snapshot) -> dict[str, object]:
    drivers = []
    for item in snapshot.drivers:
        consecutivity = item.consecutivity
        drivers.append({
            "workforce_member_id": item.workforce_member_id,
            "external_identifier": item.external_identifier,
            "display_name": item.display_name,
            "callable": item.callable,
            "callability_status": item.callability_status,
            "reason": item.callability_reason,
            "effective_consecutive_days": (
                consecutivity.effective_consecutive_days if consecutivity else None
            ),
            "planned_consecutive_days": (
                consecutivity.planned_consecutive_days if consecutivity else None
            ),
            "consecutivity_status": (
                consecutivity.calculated_status if consecutivity else "dati_insufficienti"
            ),
            "override": consecutivity.override.model_dump(mode="json") if consecutivity and consecutivity.override else None,
            "expired_override": (
                consecutivity.expired_override.model_dump(mode="json")
                if consecutivity and consecutivity.expired_override else None
            ),
            "selectable": item.callable,
            "warning": item.callability_reason if item.callability_status == "limited" else None,
        })
    return {"drivers": drivers, "policy_source": "workforce"}


def planning_conflicts(snapshot, routes: list[dict[str, object]]) -> list[dict[str, object]]:
    assigned = {str(route.get("driver_id") or "") for route in routes}
    conflicts = []
    for item in snapshot.drivers:
        if item.external_identifier not in assigned or not item.consecutivity:
            continue
        cons = item.consecutivity
        if cons.expired_override and cons.calculated_status in {
            "dati_insufficienti", "limite_raggiunto", "riposo_raccomandato",
        }:
            message = "Override Workforce scaduto."
            action = "Apri il profilo Workforce e rivaluta l'override."
            blocking = True
        elif cons.calculated_status == "dati_insufficienti":
            message = "Storico insufficiente: verifica manuale richiesta."
            action = "Apri il profilo Workforce e applica un override autorizzato."
            blocking = not bool(cons.override)
        elif cons.calculated_status in {"limite_raggiunto", "riposo_raccomandato"}:
            count = cons.planned_consecutive_days or cons.effective_consecutive_days
            message = (
                "Driver al limite di consecutivita."
                if cons.calculated_status == "limite_raggiunto"
                else f"La nuova assegnazione porterebbe il driver a {count} giorni consecutivi."
            )
            action = "Pianifica un riposo o applica un override autorizzato."
            blocking = not bool(cons.override)
        elif cons.calculated_status == "attenzione":
            message = cons.reason
            action = "Verifica il prossimo riposo prima della pubblicazione."
            blocking = False
        else:
            continue
        conflicts.append({
            "code": "WORKFORCE_CONSECUTIVITY",
            "severity": "critical" if blocking else "warning",
            "message": message,
            "entity_ref": item.external_identifier,
            "blocking": blocking,
            "suggested_action": action,
            "driver": item.display_name,
            "driver_id": item.external_identifier,
            "date": snapshot.operation_date,
            "current_count": cons.effective_consecutive_days,
            "count_after_assignment": cons.planned_consecutive_days,
            "policy": {
                "warning": cons.threshold_warning,
                "rest_required": cons.threshold_rest_required,
            },
            "workforce_target": "workforce",
        })
    return conflicts
