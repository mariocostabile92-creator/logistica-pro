from collections.abc import Sequence
from datetime import date, datetime, timedelta

from app.domain.core_language import (
    HumanResource,
    OperationalUnit,
    ResourceAvailability,
    ResourceKind,
    TimeWindow,
)
from app.domain.planning_inputs import (
    PlanningCoverage,
    PlanningInputScope,
    PlanningInputSnapshot,
    PlanningInputType,
    PlanningResourceCapability,
    WorkforcePlanningInput,
    build_planning_input_snapshot,
)
from app.plugins.workforce.domain.models import (
    WorkforceDayStatus,
    WorkforceMember,
    WorkforceRequirement,
)
from app.plugins.workforce.infrastructure import read_repository


def _timestamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.utcoffset() is None:
        raise ValueError("Workforce timestamps must be timezone-aware.")
    return parsed


def _observed_at(
    members: Sequence[WorkforceMember],
    statuses: Sequence[WorkforceDayStatus],
    fallback: datetime,
) -> datetime:
    timestamps = [
        *(_timestamp(item.updated_at) for item in members),
        *(_timestamp(item.updated_at) for item in statuses),
    ]
    return max(timestamps, default=fallback)


def _time_windows(
    operation_date: date,
    statuses: Sequence[WorkforceDayStatus],
) -> tuple[TimeWindow, ...]:
    values = {
        (
            item.shift_code or "",
            item.start_time or "",
            item.end_time or "",
        )
        for item in statuses
        if item.shift_code or item.start_time or item.end_time
    }
    return tuple(
        TimeWindow(
            external_identifier=(
                f"{operation_date.isoformat()}:{shift or 'time-window'}:"
                f"{starts_at or 'open'}:{ends_at or 'open'}"
            ),
            starts_at=starts_at or None,
            ends_at=ends_at or None,
        )
        for shift, starts_at, ends_at in sorted(values)
    )


def _coverage(
    statuses: Sequence[WorkforceDayStatus],
    requirements: Sequence[WorkforceRequirement],
) -> PlanningCoverage | None:
    if not requirements:
        return None
    required = sum(item.required_resources for item in requirements)
    available = sum(item.availability for item in statuses)
    scheduled = sum(item.status_code == "scheduled" for item in statuses)
    unavailable = len(statuses) - available
    margin = available - required
    return PlanningCoverage(
        required=required,
        available=available,
        scheduled=scheduled,
        unavailable=unavailable,
        margin=margin,
        status="covered" if margin >= 0 else "deficit",
    )


def build_workforce_planning_input_snapshot(
    *,
    organization_id: str,
    operational_unit: OperationalUnit,
    operation_date: date,
    members: Sequence[WorkforceMember],
    statuses: Sequence[WorkforceDayStatus],
    requirements: Sequence[WorkforceRequirement],
    assessed_at: datetime,
    freshness_ttl: timedelta,
) -> PlanningInputSnapshot:
    scope = PlanningInputScope(
        organization_id=organization_id,
        operational_unit=operational_unit,
        operation_date=operation_date,
    )
    active_members = sorted(
        (item for item in members if item.active),
        key=lambda item: item.external_identifier,
    )
    members_by_id = {
        item.workforce_member_id: item for item in active_members
    }
    date_value = operation_date.isoformat()
    daily_statuses = sorted(
        (
            item
            for item in statuses
            if item.date == date_value
            and item.workforce_member_id in members_by_id
        ),
        key=lambda item: (
            members_by_id[item.workforce_member_id].external_identifier,
            item.status_id,
        ),
    )
    scoped_requirements = tuple(
        item
        for item in requirements
        if item.date == date_value
        and item.operational_unit_id
        == operational_unit.external_identifier
    )
    human_resources = tuple(
        HumanResource(
            external_identifier=item.external_identifier,
            display_name=item.display_name,
            capabilities=tuple(sorted(set(item.capabilities))),
        )
        for item in active_members
    )
    availability = tuple(
        ResourceAvailability(
            resource_identifier=(
                members_by_id[item.workforce_member_id].external_identifier
            ),
            resource_kind=ResourceKind.HUMAN_RESOURCE,
            available=item.availability,
            observed_state=item.status_code,
        )
        for item in daily_statuses
    )
    capabilities = tuple(
        PlanningResourceCapability(
            resource_identifier=item.external_identifier,
            resource_kind=ResourceKind.HUMAN_RESOURCE,
            capability=capability,
        )
        for item in active_members
        for capability in sorted(set(item.capabilities))
    )
    payload = WorkforcePlanningInput(
        human_resources=human_resources,
        availability=availability,
        capabilities=capabilities,
        coverage=_coverage(daily_statuses, scoped_requirements),
        time_windows=_time_windows(operation_date, daily_statuses),
    )
    return build_planning_input_snapshot(
        input_type=PlanningInputType.WORKFORCE,
        producer="workforce-plugin",
        contract_name="workforce-planning-input",
        scope=scope,
        payload=payload,
        observed_at=_observed_at(
            active_members,
            daily_statuses,
            assessed_at,
        ),
        assessed_at=assessed_at,
        freshness_ttl=freshness_ttl,
    )


def produce_workforce_planning_input_snapshot(
    *,
    organization_id: str,
    operational_unit: OperationalUnit,
    operation_date: date,
    assessed_at: datetime,
    freshness_ttl: timedelta,
) -> PlanningInputSnapshot:
    date_value = operation_date.isoformat()
    return build_workforce_planning_input_snapshot(
        organization_id=organization_id,
        operational_unit=operational_unit,
        operation_date=operation_date,
        members=read_repository.list_members(),
        statuses=read_repository.list_statuses(date_value, date_value),
        requirements=read_repository.list_requirements(
            date_value,
            date_value,
        ),
        assessed_at=assessed_at,
        freshness_ttl=freshness_ttl,
    )
