from collections import defaultdict
from collections.abc import Callable, Mapping, Sequence
from datetime import date as CalendarDate

from app.domain.core_language import OperationalUnit
from app.domain.workforce_auto_planning import WorkforceCandidateSnapshot
from app.plugins.workforce.application.availability_service import (
    readiness_for_period,
)
from app.plugins.workforce.application.consecutivity_service import (
    snapshots_for_period,
)
from app.plugins.workforce.application.workforce_candidate_mapper import (
    map_workforce_candidate,
)
from app.plugins.workforce.domain.consecutivity import ConsecutivitySnapshot
from app.plugins.workforce.domain.driver_shift_planning import (
    DriverShiftPlanningPublishedRow,
)
from app.plugins.workforce.domain.models import (
    WorkforceDriverReadiness,
    WorkforceMember,
)
from app.plugins.workforce.infrastructure import (
    driver_shift_planning_repository,
    read_repository,
)


MemberLoader = Callable[[str], Sequence[WorkforceMember]]
ConsecutivityBatch = Callable[..., Mapping[str, Mapping[int, ConsecutivitySnapshot]]]
AvailabilityBatch = Callable[
    ...,
    Mapping[str, Sequence[WorkforceDriverReadiness]],
]
PublishedShiftBatch = Callable[
    [str, str, str],
    Sequence[DriverShiftPlanningPublishedRow],
]
CandidateMapper = Callable[..., WorkforceCandidateSnapshot]


class WorkforceCandidateSnapshotProviderAdapter:
    def __init__(
        self,
        *,
        member_loader: MemberLoader = read_repository.list_active_members_strict,
        consecutivity_batch: ConsecutivityBatch = snapshots_for_period,
        availability_batch: AvailabilityBatch = readiness_for_period,
        published_shift_batch: PublishedShiftBatch = (
            driver_shift_planning_repository.list_active_published_shifts
        ),
        candidate_mapper: CandidateMapper = map_workforce_candidate,
    ) -> None:
        self._member_loader = member_loader
        self._consecutivity_batch = consecutivity_batch
        self._availability_batch = availability_batch
        self._published_shift_batch = published_shift_batch
        self._candidate_mapper = candidate_mapper

    def get_candidates(
        self,
        *,
        organization_id: str,
        period_start: CalendarDate,
        period_end: CalendarDate,
        operational_unit: OperationalUnit,
    ) -> tuple[WorkforceCandidateSnapshot, ...]:
        period_start_iso = period_start.isoformat()
        period_end_iso = period_end.isoformat()

        loaded_members = tuple(self._member_loader(organization_id))
        if any(
            member.organization_id != organization_id
            for member in loaded_members
        ):
            raise ValueError("member loader returned a different organization")
        members = tuple(sorted(
            (member for member in loaded_members if member.active),
            key=lambda member: (
                member.external_identifier,
                member.workforce_member_id,
            ),
        ))

        consecutivity_by_date = self._consecutivity_batch(
            organization_id,
            period_start_iso,
            period_end_iso,
            members,
        )
        readiness_by_date = self._availability_batch(
            organization_id=organization_id,
            period_start=period_start_iso,
            period_end=period_end_iso,
            members=members,
            consecutivity_by_date=consecutivity_by_date,
        )
        published_assignments = self._published_shift_batch(
            organization_id,
            period_start_iso,
            period_end_iso,
        )

        readiness_by_member: dict[
            int,
            dict[str, WorkforceDriverReadiness],
        ] = defaultdict(dict)
        for operation_date, readiness_items in readiness_by_date.items():
            for readiness in readiness_items:
                readiness_by_member[readiness.workforce_member_id][
                    operation_date
                ] = readiness

        assignments_by_member: dict[
            int,
            list[DriverShiftPlanningPublishedRow],
        ] = defaultdict(list)
        for assignment in published_assignments:
            assignments_by_member[assignment.workforce_member_id].append(
                assignment
            )

        baseline = consecutivity_by_date.get(period_start_iso, {})
        candidates = []
        for member in members:
            candidates.append(self._candidate_mapper(
                member=member,
                requested_unit=operational_unit,
                readiness_by_date=readiness_by_member.get(
                    member.workforce_member_id,
                    {},
                ),
                baseline_consecutivity=baseline.get(
                    member.workforce_member_id
                ),
                published_assignments=assignments_by_member.get(
                    member.workforce_member_id,
                    (),
                ),
            ))
        return tuple(candidates)
