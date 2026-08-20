from collections import defaultdict
from collections.abc import Mapping, Sequence
from datetime import date

from app.plugins.workforce.domain.consecutivity import ConsecutivitySnapshot
from app.plugins.workforce.domain.models import (
    WorkforceDriverReadiness,
    WorkforceFoundationSnapshot,
    WorkforceFoundationSummary,
    WorkforceMember,
)
from app.plugins.workforce.infrastructure import read_repository
from app.plugins.workforce.application.consecutivity_service import (
    snapshots as consecutivity_snapshots,
)


CALLABLE_STATUSES = {"available", "scheduled"}
LIMITED_STATUSES = {"available_limited"}
KNOWN_STATUSES = CALLABLE_STATUSES | LIMITED_STATUSES | {
    "rest", "holiday", "sickness", "leave", "unavailable", "unknown"
}
AVAILABILITY_LABELS = {
    "available": "Disponibile",
    "scheduled": "Disponibile",
    "available_limited": "Disponibile con limitazioni",
    "rest": "Riposo",
    "holiday": "Ferie",
    "sickness": "Malattia",
    "leave": "Permesso",
    "unavailable": "Non disponibile",
    "unknown": "Da verificare",
}
DEFAULT_REASONS = {
    "available": "Nessuna limitazione.",
    "scheduled": "Nessuna limitazione.",
    "available_limited": "Limitazione operativa dichiarata.",
    "rest": "Riposo pianificato.",
    "holiday": "Ferie.",
    "sickness": "Malattia.",
    "leave": "Permesso.",
    "unavailable": "Indisponibilita dichiarata.",
    "unknown": "Disponibilita non dichiarata.",
}


def _decision(status: str, notes: str | None, reserve: bool, consecutivity=None) -> dict[str, object]:
    if status not in CALLABLE_STATUSES | LIMITED_STATUSES:
        return {
            "status": "not_callable", "label": "Non convocabile",
            "tone": "rest" if status == "rest" else "danger", "callable": False,
            "reason": notes.strip() if notes and notes.strip() else DEFAULT_REASONS[status],
        }
    if consecutivity and consecutivity.override:
        target = consecutivity.override.target_callability
        return {
            "status": target,
            "label": {
                "callable": "Convocabile", "limited": "Convocabile con limitazioni",
                "not_callable": "Non convocabile",
            }[target],
            "tone": {"callable": "success", "limited": "warning", "not_callable": "danger"}[target],
            "callable": target != "not_callable",
            "reason": f"Override autorizzato: {consecutivity.override.reason}",
        }
    if consecutivity:
        if consecutivity.calculated_status == "dati_insufficienti":
            return {
                "status": "not_callable", "label": "Verifica manuale richiesta",
                "tone": "danger", "callable": False,
                "reason": "Convocabilita manuale richiesta: storico consecutivita incompleto.",
            }
        if consecutivity.calculated_status in {"limite_raggiunto", "riposo_raccomandato"}:
            return {
                "status": "not_callable", "label": "Non convocabile",
                "tone": "danger", "callable": False, "reason": consecutivity.reason,
            }
        if consecutivity.calculated_status == "attenzione":
            return {
                "status": "limited", "label": "Convocabile con limitazioni",
                "tone": "warning", "callable": True, "reason": consecutivity.reason,
            }
    if status in LIMITED_STATUSES:
        return {
            "status": "limited", "label": "Convocabile con limitazioni",
            "tone": "warning", "callable": True,
            "reason": notes.strip() if notes and notes.strip() else DEFAULT_REASONS[status],
        }
    if status in CALLABLE_STATUSES:
        return {
            "status": "callable", "label": "Convocabile",
            "tone": "reserve" if reserve else "success", "callable": True,
            "reason": "Disponibile come riserva." if reserve else DEFAULT_REASONS[status],
        }
    raise ValueError("Stato Workforce non classificato.")


def _history_item(item) -> dict[str, str | bool | None]:
    status = item.status_code if item.status_code in KNOWN_STATUSES else "unknown"
    decision = _decision(status, item.notes, False)
    return {
        "date": item.date,
        "availability_status": status,
        "availability_label": AVAILABILITY_LABELS[status],
        "callability_status": str(decision["status"]),
        "callability_label": str(decision["label"]),
        "reason": str(decision["reason"]),
        "updated_at": item.updated_at,
        "manual": item.observed_or_confirmed.value == "manual",
    }


def _readiness_for_date(
    target_date: str,
    members: Sequence[WorkforceMember],
    statuses,
    consecutivity_by_member: Mapping[int, ConsecutivitySnapshot | None],
) -> tuple[list[WorkforceDriverReadiness], set[str]]:
    history_by_member = defaultdict(list)
    daily_by_member = {}
    for item in statuses:
        if item.date > target_date:
            continue
        history_by_member[item.workforce_member_id].append(item)
        if item.date == target_date:
            daily_by_member[item.workforce_member_id] = item

    drivers = []
    unknown_statuses: set[str] = set()
    for member in members:
        if not member.active:
            continue
        daily = daily_by_member.get(member.workforce_member_id)
        status = daily.status_code if daily else "unknown"
        if status not in KNOWN_STATUSES:
            unknown_statuses.add(status)
            status = "unknown"
        consecutivity = consecutivity_by_member[member.workforce_member_id]
        decision = _decision(
            status, daily.notes if daily else None, member.is_reserve, consecutivity
        )
        history = sorted(
            history_by_member[member.workforce_member_id],
            key=lambda item: (item.date, item.updated_at), reverse=True,
        )[:10]
        limitations = (
            [str(decision["reason"])] if decision["status"] == "limited" else []
        )
        drivers.append(WorkforceDriverReadiness(
            workforce_member_id=member.workforce_member_id,
            external_identifier=member.external_identifier,
            first_name=member.first_name or member.display_name,
            last_name=member.last_name or "",
            display_name=member.display_name,
            role=member.role,
            station=member.station,
            contract=member.employment_type,
            operational_cycle=member.operational_cycle,
            availability_status=status,
            availability_label=AVAILABILITY_LABELS[status],
            callability_status=str(decision["status"]),
            callability_label=str(decision["label"]),
            callability_reason=str(decision["reason"]),
            callability_tone=str(decision["tone"]),
            callable=bool(decision["callable"]),
            is_reserve=member.is_reserve,
            rest=status == "rest",
            holiday=status == "holiday",
            sickness=status == "sickness",
            leave=status == "leave",
            consecutive_days=(
                consecutivity.effective_consecutive_days if consecutivity else None
            ),
            consecutivity_status=(
                consecutivity.calculated_status if consecutivity else "not_evaluated"
            ),
            consecutivity=consecutivity,
            capabilities=member.capabilities,
            operational_notes=member.operational_notes,
            convocation_status="not_started" if decision["callable"] else "not_applicable",
            limitations=limitations,
            status_history=[_history_item(item) for item in history],
            last_updated_at=daily.updated_at if daily else member.updated_at,
        ))
    drivers.sort(key=lambda item: (
        {"limited": 0, "callable": 1, "not_callable": 2}[item.callability_status],
        not item.is_reserve, item.display_name.casefold(),
    ))
    return drivers, unknown_statuses


def foundation_snapshot(
    operation_date: str | None = None,
    organization_id: str = "default",
) -> WorkforceFoundationSnapshot:
    target_date = operation_date or date.today().isoformat()
    date.fromisoformat(target_date)
    all_statuses = read_repository.list_statuses(
        date_to=target_date, organization_id=organization_id
    )
    members = read_repository.list_members(organization_id=organization_id)
    consecutivity_by_member = consecutivity_snapshots(
        organization_id, target_date, members
    )
    drivers, unknown_statuses = _readiness_for_date(
        target_date, members, all_statuses, consecutivity_by_member
    )
    summary = WorkforceFoundationSummary(
        total=len(drivers),
        available=sum(item.availability_status in CALLABLE_STATUSES | LIMITED_STATUSES for item in drivers),
        callable=sum(item.callable for item in drivers),
        limited=sum(item.callability_status == "limited" for item in drivers),
        holiday=sum(item.holiday for item in drivers),
        sickness=sum(item.sickness for item in drivers),
        leave=sum(item.leave for item in drivers),
        rest=sum(item.rest for item in drivers),
        not_callable=sum(not item.callable for item in drivers),
        reserves=sum(item.is_reserve and item.callable for item in drivers),
        at_limit=sum(item.consecutivity_status == "limite_raggiunto" for item in drivers),
        rest_recommended=sum(item.consecutivity_status == "riposo_raccomandato" for item in drivers),
        insufficient_data=sum(item.consecutivity_status == "dati_insufficienti" for item in drivers),
        active_overrides=sum(bool(item.consecutivity and item.consecutivity.override) for item in drivers),
    )
    limitations = [
        "Valutazione basata sulla policy operativa dell'organizzazione.",
        "Le convocazioni appartengono al Planning e non vengono eseguite da Workforce.",
    ]
    if unknown_statuses:
        limitations.append("Sono presenti stati sorgente non classificati.")
    return WorkforceFoundationSnapshot(
        operation_date=target_date, summary=summary, drivers=drivers,
        limitations=limitations,
    )


def readiness_for_period(
    *,
    organization_id: str,
    period_start: str,
    period_end: str,
    members: Sequence[WorkforceMember],
    consecutivity_by_date: Mapping[
        str, Mapping[int, ConsecutivitySnapshot | None]
    ],
) -> dict[str, tuple[WorkforceDriverReadiness, ...]]:
    if not isinstance(organization_id, str) or not organization_id.strip():
        raise ValueError("organization_id is required")
    start = date.fromisoformat(period_start)
    end = date.fromisoformat(period_end)
    if end < start:
        raise ValueError("period_end must not be before period_start")

    ordered_members = tuple(sorted(
        members,
        key=lambda item: (item.workforce_member_id, item.external_identifier),
    ))
    if any(member.organization_id != organization_id for member in ordered_members):
        raise ValueError("members must belong to organization_id")

    for operation_date, items in consecutivity_by_date.items():
        for member_id, snapshot in items.items():
            if snapshot is None:
                continue
            if snapshot.organization_id != organization_id:
                raise ValueError("consecutivity must belong to organization_id")
            if snapshot.operation_date != operation_date:
                raise ValueError("consecutivity operation_date does not match its index")
            if snapshot.driver_id != member_id:
                raise ValueError("consecutivity driver_id does not match its index")

    member_ids = tuple(member.workforce_member_id for member in ordered_members)
    statuses = read_repository.list_statuses_strict(
        organization_id,
        date_to=period_end,
        member_ids=member_ids,
    )
    result = {}
    cursor = start
    while cursor <= end:
        operation_date = cursor.isoformat()
        indexed = consecutivity_by_date.get(operation_date, {})
        daily_consecutivity = {
            member.workforce_member_id: indexed.get(member.workforce_member_id)
            for member in ordered_members
        }
        drivers, _unknown_statuses = _readiness_for_date(
            operation_date,
            ordered_members,
            statuses,
            daily_consecutivity,
        )
        result[operation_date] = tuple(drivers)
        cursor = date.fromordinal(cursor.toordinal() + 1)
    return result
