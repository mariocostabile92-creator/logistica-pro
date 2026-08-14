from collections import defaultdict
from dataclasses import replace
from datetime import date, timedelta

from app.plugins.workforce.domain.coverage import (
    ForecastAuthorityStatus,
    ForecastDetectionReason,
    ImportedDailyCoverageRequirement,
)


MIN_TEMPLATE_RUN_DAYS = 14


def _bucket_key(
    item: ImportedDailyCoverageRequirement,
) -> tuple[str, str, str]:
    return (
        str(item.station or "").strip().casefold(),
        item.operational_cycle,
        str(item.coverage_segment or "").strip().upper(),
    )


def _date(value: str) -> date:
    return date.fromisoformat(value)


def _arithmetic_runs(
    indexed: dict[date, int],
    requirements: list[ImportedDailyCoverageRequirement],
    minimum_days: int,
) -> list[tuple[date, date]]:
    if not indexed:
        return []
    current = min(indexed)
    end = max(indexed)
    run_start: date | None = None
    previous_value: int | None = None
    previous_day: date | None = None
    runs: list[tuple[date, date]] = []

    def finish(last_day: date | None) -> None:
        nonlocal run_start
        if run_start is None or last_day is None:
            run_start = None
            return
        if (last_day - run_start).days + 1 >= minimum_days:
            runs.append((run_start, last_day))
        run_start = None

    while current <= end:
        item_index = indexed.get(current)
        if item_index is None:
            finish(previous_day)
            previous_value = None
            previous_day = None
            current += timedelta(days=1)
            continue
        value = requirements[item_index].forecast_routes
        if previous_day == current - timedelta(days=1) and value == previous_value + 1:
            if run_start is None:
                run_start = previous_day
        else:
            finish(previous_day)
        previous_value = value
        previous_day = current
        current += timedelta(days=1)
    finish(previous_day)
    return runs


def _constant_over_interval(
    indexed: dict[date, int],
    requirements: list[ImportedDailyCoverageRequirement],
    start: date,
    end: date,
    minimum_days: int,
) -> list[int]:
    indices: list[int] = []
    current = start
    expected: int | None = None
    while current <= end:
        item_index = indexed.get(current)
        if item_index is None:
            return []
        value = requirements[item_index].forecast_routes
        if expected is None:
            expected = value
        elif value != expected:
            return []
        indices.append(item_index)
        current += timedelta(days=1)
    return indices if len(indices) >= minimum_days else []


def classify_forecast_requirements(
    requirements: list[ImportedDailyCoverageRequirement],
    *,
    minimum_days: int = MIN_TEMPLATE_RUN_DAYS,
) -> list[ImportedDailyCoverageRequirement]:
    """Classify template-like forecast ranges in O(days + requirements).

    The parser already supplies one requirement per bucket/day. Date-indexed
    walks avoid pairwise comparisons and keep annual workbooks linear.
    """
    if minimum_days < 2:
        raise ValueError("minimum_days deve essere almeno 2.")
    classified = list(requirements)
    groups: dict[tuple[str, str, str], dict[date, int]] = defaultdict(dict)
    for index, item in enumerate(classified):
        groups[_bucket_key(item)][_date(item.operational_date)] = index

    rejected_intervals: dict[str, list[tuple[date, date]]] = defaultdict(list)
    for (station, cycle, segment), indexed in groups.items():
        if cycle != "NEXT_DAY" or segment:
            continue
        for start, end in _arithmetic_runs(
            indexed, classified, minimum_days
        ):
            rejected_intervals[station].append((start, end))
            current = start
            while current <= end:
                item_index = indexed[current]
                classified[item_index] = replace(
                    classified[item_index],
                    authority_status=ForecastAuthorityStatus.REJECTED_TEMPLATE.value,
                    detection_reason=(
                        ForecastDetectionReason.LONG_ARITHMETIC_SEQUENCE.value
                    ),
                )
                current += timedelta(days=1)

    for station, intervals in rejected_intervals.items():
        for segment in ("A", "B_C"):
            indexed = groups.get((station, "SAME_DAY", segment), {})
            for start, end in intervals:
                for item_index in _constant_over_interval(
                    indexed, classified, start, end, minimum_days
                ):
                    classified[item_index] = replace(
                        classified[item_index],
                        authority_status=(
                            ForecastAuthorityStatus.SUSPECT_TEMPLATE.value
                        ),
                        detection_reason=(
                            ForecastDetectionReason.CORRELATED_CONSTANT_BLOCK.value
                        ),
                    )
    return classified
