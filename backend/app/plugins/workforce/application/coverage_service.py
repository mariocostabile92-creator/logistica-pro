from datetime import date, timedelta

from app.plugins.workforce.domain.coverage import (
    CoverageStatus,
    DailyCoverageReadModel,
    DailyCoverageResponse,
    DailyCoverageSummary,
)
from app.plugins.workforce.infrastructure import coverage_repository


_BUCKETS: tuple[tuple[str, str | None, frozenset[str]], ...] = (
    ("NEXT_DAY", None, frozenset({"C1", "L1", "L2", "L3", "VMC1"})),
    ("SAME_DAY", "A", frozenset({"SA"})),
    ("SAME_DAY", "B_C", frozenset({"SB"})),
)
_BUCKET_CODES = {
    (cycle, segment): codes for cycle, segment, codes in _BUCKETS
}
_CYCLE_ORDER = {"NEXT_DAY": 0, "SAME_DAY": 1}


def _dates(date_from: str, date_to: str) -> list[str]:
    start = date.fromisoformat(date_from)
    end = date.fromisoformat(date_to)
    if end < start:
        raise ValueError("date_to non può precedere date_from.")
    return [
        (start + timedelta(days=offset)).isoformat()
        for offset in range((end - start).days + 1)
    ]


def _assigned(
    groups: list[dict[str, object]],
    *,
    operational_date: str,
    cycle: str,
    segment: str | None,
    station: str | None,
) -> int:
    codes = _BUCKET_CODES.get((cycle, segment), frozenset())
    if not codes:
        return 0
    normalized_station = str(station or "").strip().casefold()
    return sum(
        int(item["assigned"])
        for item in groups
        if item["date"] == operational_date
        and item["operational_cycle"] == cycle
        and item["shift_code"] in codes
        and (
            not normalized_station
            or str(item["station"] or "").strip().casefold()
            == normalized_station
        )
    )


def _read_model(
    *,
    operational_date: str,
    cycle: str,
    segment: str | None,
    station: str | None,
    assigned_drivers: int,
    forecast_routes: int | None = None,
    reserve_percentage: int | None = None,
    required_capacity: int | None = None,
    source: str | None = None,
    source_reference: str | None = None,
) -> DailyCoverageReadModel:
    if forecast_routes is None or required_capacity is None:
        return DailyCoverageReadModel(
            operational_date=operational_date,
            cycle=cycle,
            segment=segment,
            station=station,
            assigned_drivers=assigned_drivers,
            coverage_status=CoverageStatus.NO_FORECAST,
        )
    forecast_gap = max(forecast_routes - assigned_drivers, 0)
    requirement_gap = max(required_capacity - assigned_drivers, 0)
    reserve_drivers = max(assigned_drivers - required_capacity, 0)
    if assigned_drivers < forecast_routes:
        status = CoverageStatus.UNDER_FORECAST
    elif assigned_drivers < required_capacity:
        status = CoverageStatus.FORECAST_COVERED
    else:
        status = CoverageStatus.REQUIREMENT_COVERED
    return DailyCoverageReadModel(
        operational_date=operational_date,
        cycle=cycle,
        segment=segment,
        station=station,
        forecast_routes=forecast_routes,
        reserve_percentage=reserve_percentage,
        required_capacity=required_capacity,
        assigned_drivers=assigned_drivers,
        forecast_gap=forecast_gap,
        requirement_gap=requirement_gap,
        reserve_drivers=reserve_drivers,
        coverage_status=status,
        source=source,
        source_reference=source_reference,
    )


def daily_coverage(
    organization_id: str,
    date_from: str,
    date_to: str,
    cycle: str | None = None,
) -> DailyCoverageResponse:
    if cycle not in {None, "NEXT_DAY", "SAME_DAY"}:
        raise ValueError("Ciclo operativo non supportato.")
    days = _dates(date_from, date_to)
    requirements = coverage_repository.list_current_requirements(
        organization_id, date_from, date_to, cycle
    )
    groups = coverage_repository.assigned_driver_groups(
        organization_id, date_from, date_to
    )
    items: list[DailyCoverageReadModel] = []
    covered_bucket_dates: set[tuple[str, str, str | None]] = set()
    for requirement in requirements:
        key = (
            requirement.operational_date,
            requirement.operational_cycle,
            requirement.coverage_segment,
        )
        covered_bucket_dates.add(key)
        assigned = _assigned(
            groups,
            operational_date=requirement.operational_date,
            cycle=requirement.operational_cycle,
            segment=requirement.coverage_segment,
            station=requirement.station,
        )
        items.append(_read_model(
            operational_date=requirement.operational_date,
            cycle=requirement.operational_cycle,
            segment=requirement.coverage_segment,
            station=requirement.station,
            forecast_routes=requirement.forecast_routes,
            reserve_percentage=requirement.reserve_percentage,
            required_capacity=requirement.required_capacity,
            assigned_drivers=assigned,
            source=requirement.source,
            source_reference=requirement.source_reference,
        ))
    expected_buckets = [
        (bucket_cycle, segment)
        for bucket_cycle, segment, _ in _BUCKETS
        if cycle is None or bucket_cycle == cycle
    ]
    for operational_date in days:
        for bucket_cycle, segment in expected_buckets:
            if (operational_date, bucket_cycle, segment) in covered_bucket_dates:
                continue
            items.append(_read_model(
                operational_date=operational_date,
                cycle=bucket_cycle,
                segment=segment,
                station=None,
                assigned_drivers=_assigned(
                    groups,
                    operational_date=operational_date,
                    cycle=bucket_cycle,
                    segment=segment,
                    station=None,
                ),
            ))
    items.sort(key=lambda item: (
        item.operational_date,
        _CYCLE_ORDER.get(item.cycle, 99),
        item.segment or "",
        item.station or "",
    ))
    forecast_items = [item for item in items if item.forecast_routes is not None]
    summary = DailyCoverageSummary(
        forecast_total=sum(item.forecast_routes or 0 for item in forecast_items),
        requirement_total=sum(
            item.required_capacity or 0 for item in forecast_items
        ),
        assigned_total=sum(item.assigned_drivers for item in items),
        forecast_gap_total=sum(item.forecast_gap or 0 for item in forecast_items),
        requirement_gap_total=sum(
            item.requirement_gap or 0 for item in forecast_items
        ),
        reserve_total=sum(item.reserve_drivers or 0 for item in forecast_items),
        forecast_available_buckets=len(forecast_items),
        no_forecast_buckets=sum(
            item.coverage_status == CoverageStatus.NO_FORECAST for item in items
        ),
    )
    return DailyCoverageResponse(
        date_from=date_from,
        date_to=date_to,
        cycle=cycle,
        items=items,
        summary=summary,
    )
