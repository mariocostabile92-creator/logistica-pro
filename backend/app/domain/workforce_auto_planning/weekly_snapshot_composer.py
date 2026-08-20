from dataclasses import dataclass
from datetime import date as CalendarDate, datetime

from app.domain.core_language import OperationalUnit
from app.domain.workforce_auto_planning.snapshot_provider_ports import (
    OperationalDemandProvider,
    WorkforceCandidateSnapshotProvider,
)
from app.domain.workforce_auto_planning.weekly_planning_input_snapshot import (
    WeeklyPlanningInputSnapshot,
)
from app.domain.workforce_auto_planning.weekly_snapshot_fingerprint import (
    compute_weekly_planning_input_fingerprint,
)


@dataclass(frozen=True, slots=True)
class WeeklyPlanningInputSnapshotComposer:
    demand_provider: OperationalDemandProvider
    candidate_provider: WorkforceCandidateSnapshotProvider

    def compose(
        self,
        *,
        snapshot_id: str,
        organization_id: str,
        period_start: CalendarDate,
        period_end: CalendarDate,
        operational_unit: OperationalUnit,
        policy_set_identifier: str,
        policy_set_version: str,
        created_at: datetime,
    ) -> WeeklyPlanningInputSnapshot:
        demands = self.demand_provider.get_demands(
            organization_id=organization_id,
            period_start=period_start,
            period_end=period_end,
            operational_unit=operational_unit,
        )
        candidates = self.candidate_provider.get_candidates(
            organization_id=organization_id,
            period_start=period_start,
            period_end=period_end,
            operational_unit=operational_unit,
        )
        fingerprint = compute_weekly_planning_input_fingerprint(
            organization_id=organization_id,
            period_start=period_start,
            period_end=period_end,
            operational_unit=operational_unit,
            demands=demands,
            workforce_candidates=candidates,
            policy_set_identifier=policy_set_identifier,
            policy_set_version=policy_set_version,
        )
        return WeeklyPlanningInputSnapshot(
            snapshot_id=snapshot_id,
            organization_id=organization_id,
            period_start=period_start,
            period_end=period_end,
            operational_unit=operational_unit,
            demands=demands,
            workforce_candidates=candidates,
            policy_set_identifier=policy_set_identifier,
            policy_set_version=policy_set_version,
            created_at=created_at,
            fingerprint=fingerprint,
        )
