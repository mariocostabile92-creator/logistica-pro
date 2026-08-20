from collections.abc import Mapping, Sequence
from datetime import date, datetime, time
from decimal import Decimal

from app.domain.core_language import (
    HumanResource,
    OperationalUnit,
    ResourceAvailability,
    ResourceKind,
    TimeWindow,
)
from app.domain.workforce_auto_planning import (
    ApprovedAssignmentSnapshot,
    AssignedTimeSnapshot,
    AssignedTimeStatus,
    AssignedTimeUnit,
    CandidateOperationalUnitScope,
    CandidateOperationalUnitScopeStatus,
    ConstraintEvidence,
    CurrentMemberContractStateSnapshot,
    WorkforceCandidateAvailabilitySnapshot,
    WorkforceCandidateSnapshot,
)
from app.plugins.workforce.domain.consecutivity import ConsecutivitySnapshot
from app.plugins.workforce.domain.driver_shift_planning import (
    DriverShiftPlanningPublishedRow,
)
from app.plugins.workforce.domain.models import (
    WorkforceDriverReadiness,
    WorkforceMember,
)


def _contract_date(value: str | None) -> date | None:
    return date.fromisoformat(value) if value is not None else None


def _operational_unit_scope(
    member: WorkforceMember,
    requested_unit: OperationalUnit,
) -> CandidateOperationalUnitScope:
    if member.station is None or not member.station.strip():
        return CandidateOperationalUnitScope(
            status=CandidateOperationalUnitScopeStatus.UNKNOWN,
            requested_unit=requested_unit,
        )
    candidate_unit = OperationalUnit(external_identifier=member.station)
    status = (
        CandidateOperationalUnitScopeStatus.MATCHED
        if member.station == requested_unit.external_identifier
        else CandidateOperationalUnitScopeStatus.MISMATCHED
    )
    return CandidateOperationalUnitScope(
        status=status,
        requested_unit=requested_unit,
        candidate_unit=candidate_unit,
    )


def _known_duration_minutes(
    start_time: str | None,
    end_time: str | None,
) -> Decimal | None:
    if start_time is None or end_time is None:
        return None
    try:
        start = time.fromisoformat(start_time)
        end = time.fromisoformat(end_time)
    except ValueError:
        return None
    if start.tzinfo is not None or end.tzinfo is not None or end <= start:
        return None
    delta = datetime.combine(date.min, end) - datetime.combine(date.min, start)
    return (
        Decimal(delta.seconds) / Decimal(60)
        + Decimal(delta.microseconds) / Decimal(60_000_000)
    )


def _assignment_reference(row: DriverShiftPlanningPublishedRow) -> str:
    return (
        f"driver-shift-planning:{row.driver_shift_planning_id}:"
        f"v{row.planning_version}:published-row:{row.id}"
    )


def _approved_assignment(
    row: DriverShiftPlanningPublishedRow,
) -> tuple[ApprovedAssignmentSnapshot, Decimal | None]:
    reference = _assignment_reference(row)
    duration = _known_duration_minutes(row.start_time, row.end_time)
    assigned_time = (
        AssignedTimeSnapshot(
            status=AssignedTimeStatus.KNOWN,
            value=duration,
            unit=AssignedTimeUnit.MINUTES,
        )
        if duration is not None
        else AssignedTimeSnapshot(status=AssignedTimeStatus.UNKNOWN)
    )
    assignment_unit = (
        OperationalUnit(external_identifier=row.station)
        if row.station is not None and row.station.strip()
        else None
    )
    return (
        ApprovedAssignmentSnapshot(
            assignment_reference=reference,
            date=date.fromisoformat(row.operational_date),
            operational_unit=assignment_unit,
            shift_identifier=row.shift_code,
            time_window=TimeWindow(
                external_identifier=f"{reference}:time-window",
                starts_at=row.start_time,
                ends_at=row.end_time,
            ),
            assigned_time=assigned_time,
        ),
        duration,
    )


def _aggregate_assigned_time(
    durations: Sequence[Decimal | None],
) -> AssignedTimeSnapshot:
    if not durations:
        return AssignedTimeSnapshot(
            status=AssignedTimeStatus.KNOWN,
            value=Decimal(0),
            unit=AssignedTimeUnit.MINUTES,
        )
    known = tuple(value for value in durations if value is not None)
    if not known:
        return AssignedTimeSnapshot(status=AssignedTimeStatus.UNKNOWN)
    return AssignedTimeSnapshot(
        status=(
            AssignedTimeStatus.KNOWN
            if len(known) == len(durations)
            else AssignedTimeStatus.PARTIAL
        ),
        value=sum(known, start=Decimal(0)),
        unit=AssignedTimeUnit.MINUTES,
    )


def map_workforce_candidate(
    *,
    member: WorkforceMember,
    requested_unit: OperationalUnit,
    readiness_by_date: Mapping[str, WorkforceDriverReadiness],
    baseline_consecutivity: ConsecutivitySnapshot | None,
    published_assignments: Sequence[DriverShiftPlanningPublishedRow],
    evidence: Sequence[ConstraintEvidence] = (),
) -> WorkforceCandidateSnapshot:
    availability_items = []
    generated_evidence = []
    for operation_date, readiness in sorted(readiness_by_date.items()):
        if readiness.workforce_member_id != member.workforce_member_id:
            raise ValueError("readiness must belong to the workforce member")
        if readiness.external_identifier != member.external_identifier:
            raise ValueError("readiness external_identifier does not match member")
        availability_items.append(
            WorkforceCandidateAvailabilitySnapshot(
                date=date.fromisoformat(operation_date),
                availability=ResourceAvailability(
                    resource_identifier=member.external_identifier,
                    resource_kind=ResourceKind.HUMAN_RESOURCE,
                    available=readiness.callable,
                    observed_state=readiness.availability_status,
                    reason=readiness.callability_reason,
                    origin="workforce-readiness",
                ),
            )
        )
        generated_evidence.append(
            ConstraintEvidence(
                key=f"workforce-readiness:{operation_date}:callability-status",
                value=readiness.callability_status,
            )
        )
        generated_evidence.extend(
            ConstraintEvidence(
                key=f"workforce-readiness:{operation_date}:limitation:{index}",
                value=limitation,
            )
            for index, limitation in enumerate(readiness.limitations, start=1)
        )

    if baseline_consecutivity is not None:
        if baseline_consecutivity.organization_id != member.organization_id:
            raise ValueError("consecutivity must belong to the member organization")
        if baseline_consecutivity.driver_id != member.workforce_member_id:
            raise ValueError("consecutivity must belong to the workforce member")

    ordered_rows = tuple(sorted(
        published_assignments,
        key=lambda row: (
            row.operational_date,
            row.workforce_member_id,
            row.shift_code or "",
            row.id,
        ),
    ))
    approved_assignments = []
    durations = []
    for row in ordered_rows:
        if row.organization_id != member.organization_id:
            raise ValueError("published assignment must belong to member organization")
        if row.workforce_member_id != member.workforce_member_id:
            raise ValueError("published assignment must belong to workforce member")
        assignment, duration = _approved_assignment(row)
        approved_assignments.append(assignment)
        durations.append(duration)

    contract_state = CurrentMemberContractStateSnapshot(
        employment_type=member.employment_type,
        contract_start=_contract_date(member.contract_start),
        contract_end=_contract_date(member.contract_end),
        weekly_hours=(
            Decimal(str(member.weekly_hours))
            if member.weekly_hours is not None
            else None
        ),
        is_reserve=member.is_reserve,
    )
    human_resource = HumanResource(
        external_identifier=member.external_identifier,
        display_name=member.display_name,
        capabilities=tuple(member.capabilities),
    )
    return WorkforceCandidateSnapshot(
        organization_id=member.organization_id,
        human_resource=human_resource,
        availability=tuple(availability_items),
        applicable_contract_state=contract_state,
        operational_unit_scope=_operational_unit_scope(member, requested_unit),
        recent_consecutivity=(
            baseline_consecutivity.effective_consecutive_days
            if baseline_consecutivity is not None
            else None
        ),
        already_approved_assignments=tuple(approved_assignments),
        already_assigned_minutes_or_hours=_aggregate_assigned_time(durations),
        evidence=tuple(evidence) + tuple(generated_evidence),
    )
