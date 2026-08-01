from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


class OperationalDayError(ValueError):
    pass


def organization_timezone(value: str | None) -> ZoneInfo:
    try:
        return ZoneInfo(value or "Europe/Rome")
    except ZoneInfoNotFoundError as exc:
        raise OperationalDayError("Timezone organizzazione non valida.") from exc


def start_hour(value: object) -> int:
    try:
        hour = int(value if value is not None else 4)
    except (TypeError, ValueError) as exc:
        raise OperationalDayError("Ora di inizio giornata operativa non valida.") from exc
    if not 0 <= hour <= 23:
        raise OperationalDayError("Ora di inizio giornata operativa non valida.")
    return hour


def operational_date(
    occurred_at: datetime,
    timezone_name: str | None,
    operational_start_hour: object = 4,
) -> date:
    if occurred_at.tzinfo is None:
        occurred_at = occurred_at.replace(tzinfo=timezone.utc)
    local = occurred_at.astimezone(organization_timezone(timezone_name))
    return (local - timedelta(hours=start_hour(operational_start_hour))).date()


def operational_bounds(
    day: date,
    timezone_name: str | None,
    operational_start_hour: object = 4,
) -> tuple[datetime, datetime]:
    zone = organization_timezone(timezone_name)
    begins = datetime.combine(day, time(start_hour(operational_start_hour)), tzinfo=zone)
    return begins.astimezone(timezone.utc), (begins + timedelta(days=1)).astimezone(timezone.utc)
