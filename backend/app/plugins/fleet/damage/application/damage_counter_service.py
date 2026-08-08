from datetime import date, datetime

from app.plugins.fleet.damage.application.damage_policy_service import current_policy
from app.plugins.fleet.damage.domain.damage_policy import (
    DamageCountingPeriod,
    DamageDriverPolicyState,
    is_damage_countable,
)
from app.plugins.fleet.damage.infrastructure import damage_counter_repository


class DamagePolicyDriverNotFound(LookupError):
    pass


def _reference_date(value: date | str | None) -> date:
    if value is None:
        return date.today()
    if isinstance(value, date):
        return value
    return date.fromisoformat(value)


def period_bounds(
    period: DamageCountingPeriod,
    reference_date: date | str | None = None,
) -> tuple[date | None, date | None]:
    reference = _reference_date(reference_date)
    if period is DamageCountingPeriod.ALL_TIME:
        return None, None
    if period is DamageCountingPeriod.CALENDAR_YEAR:
        return date(reference.year, 1, 1), date(reference.year, 12, 31)
    try:
        start = reference.replace(year=reference.year - 1)
    except ValueError:
        start = reference.replace(year=reference.year - 1, day=28)
    return start, reference


def _occurred_date(damage_case: dict[str, object]) -> date:
    value = str(damage_case["occurred_at"])
    return datetime.fromisoformat(value.replace("Z", "+00:00")).date()


def countable_cases_for_period(
    cases: list[dict[str, object]],
    period: DamageCountingPeriod,
    reference_date: date | str | None = None,
) -> list[dict[str, object]]:
    start, end = period_bounds(period, reference_date)
    selected = [
        damage_case
        for damage_case in cases
        if is_damage_countable(damage_case)
        and (start is None or _occurred_date(damage_case) >= start)
        and (end is None or _occurred_date(damage_case) <= end)
    ]
    return sorted(
        selected,
        key=lambda item: (str(item["occurred_at"]), int(item["id"])),
    )


def classify_countable_events(
    countable_cases: list[dict[str, object]],
    *,
    policy_enabled: bool,
    free_events_count: int,
) -> list[tuple[dict[str, object], bool, bool]]:
    ordered = sorted(
        countable_cases,
        key=lambda item: (str(item["occurred_at"]), int(item["id"])),
    )
    return [
        (
            damage_case,
            policy_enabled and index < free_events_count,
            policy_enabled and index >= free_events_count,
        )
        for index, damage_case in enumerate(ordered)
    ]


def driver_policy_state(
    organization_id: str,
    workforce_member_id: int,
    reference_date: date | str | None = None,
) -> DamageDriverPolicyState:
    if not damage_counter_repository.driver_exists(
        organization_id, workforce_member_id
    ):
        raise DamagePolicyDriverNotFound(
            "Driver Workforce non trovato nell'organizzazione richiesta."
        )
    policy = current_policy(organization_id)
    all_cases = damage_counter_repository.list_attributed_cases(
        organization_id, workforce_member_id
    )
    countable = countable_cases_for_period(
        all_cases, policy.counting_period, reference_date
    )
    start, end = period_bounds(policy.counting_period, reference_date)
    classified = classify_countable_events(
        countable,
        policy_enabled=policy.enabled,
        free_events_count=policy.free_events_count,
    )
    free_used = sum(is_free for _, is_free, _ in classified)
    over_threshold = sum(is_over for _, _, is_over in classified)
    next_over_threshold = (
        policy.enabled and len(countable) >= policy.free_events_count
    )
    return DamageDriverPolicyState(
        workforce_member_id=workforce_member_id,
        policy_enabled=policy.enabled,
        total_attributed_cases=len(all_cases),
        countable_cases=len(countable),
        free_events_count=policy.free_events_count,
        free_events_used=free_used,
        events_over_threshold=over_threshold,
        next_event_is_over_threshold=next_over_threshold,
        counting_period=policy.counting_period,
        period_start=start,
        period_end=end,
    )
