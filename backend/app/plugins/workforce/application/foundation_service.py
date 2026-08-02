from datetime import date

from app.plugins.workforce.domain.models import (
    WorkforceDriverReadiness,
    WorkforceFoundationSnapshot,
    WorkforceFoundationSummary,
)
from app.plugins.workforce.infrastructure import read_repository


CALLABLE_STATUSES = {"available", "scheduled"}
KNOWN_STATUSES = CALLABLE_STATUSES | {
    "rest", "holiday", "sickness", "leave", "unavailable", "unknown"
}


def _status_by_member(operation_date: str):
    return {
        item.workforce_member_id: item
        for item in read_repository.list_statuses(operation_date, operation_date)
    }


def foundation_snapshot(operation_date: str | None = None) -> WorkforceFoundationSnapshot:
    target_date = operation_date or date.today().isoformat()
    date.fromisoformat(target_date)
    statuses = _status_by_member(target_date)
    drivers = []
    unknown_statuses: set[str] = set()
    for member in read_repository.list_members():
        if not member.active:
            continue
        daily = statuses.get(member.workforce_member_id)
        status = daily.status_code if daily else "unknown"
        if status not in KNOWN_STATUSES:
            unknown_statuses.add(status)
            status = "unknown"
        callable_driver = bool(daily and daily.availability and status in CALLABLE_STATUSES)
        drivers.append(
            WorkforceDriverReadiness(
                workforce_member_id=member.workforce_member_id,
                external_identifier=member.external_identifier,
                first_name=member.first_name or member.display_name,
                last_name=member.last_name or "",
                display_name=member.display_name,
                role=member.role,
                station=member.station,
                contract=member.employment_type,
                availability_status=status,
                callable=callable_driver,
                is_reserve=member.is_reserve,
                rest=status == "rest",
                holiday=status == "holiday",
                sickness=status == "sickness",
                leave=status == "leave",
                capabilities=member.capabilities,
                operational_notes=(
                    member.operational_notes or (daily.notes if daily else None)
                ),
                convocation_status=(
                    "not_started" if callable_driver else "not_applicable"
                ),
            )
        )
    drivers.sort(key=lambda item: (not item.callable, not item.is_reserve, item.display_name.casefold()))
    summary = WorkforceFoundationSummary(
        total=len(drivers),
        available=sum(item.availability_status in CALLABLE_STATUSES for item in drivers),
        callable=sum(item.callable for item in drivers),
        holiday=sum(item.holiday for item in drivers),
        sickness=sum(item.sickness for item in drivers),
        leave=sum(item.leave for item in drivers),
        rest=sum(item.rest for item in drivers),
        not_callable=sum(not item.callable for item in drivers),
        reserves=sum(item.is_reserve and item.callable for item in drivers),
    )
    limitations = [
        "La consecutivita e predisposta ma non viene ancora calcolata automaticamente.",
        "Le convocazioni appartengono al Planning e non vengono eseguite da Workforce.",
    ]
    if unknown_statuses:
        limitations.append("Sono presenti stati sorgente non classificati.")
    return WorkforceFoundationSnapshot(
        operation_date=target_date,
        summary=summary,
        drivers=drivers,
        limitations=limitations,
    )
