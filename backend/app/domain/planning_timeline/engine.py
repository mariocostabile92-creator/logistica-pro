from datetime import datetime

from app.domain.planning_conflicts import PlanningConflictReport
from app.domain.planning_inputs import PlanningInputStatus
from app.domain.planning_readiness import (
    PlanningReadinessResult,
    PlanningReadinessStatus,
)
from app.domain.planning_timeline.contracts import (
    PlanningTimelineCompositionReport,
)
from app.domain.planning_timeline.formatter import PlanningTimelineFormatter
from app.domain.planning_timeline.grouping import (
    group_planning_timeline_events,
    sort_planning_timeline_events,
)
from app.domain.planning_timeline.models import (
    PlanningTimelineCategory,
    PlanningTimelineReport,
    PlanningTimelineResult,
    PlanningTimelineSeverity,
)


def _snapshot_severity(status: PlanningInputStatus):
    if status is PlanningInputStatus.READY:
        return PlanningTimelineSeverity.SUCCESS
    if status in {PlanningInputStatus.PARTIAL, PlanningInputStatus.STALE}:
        return PlanningTimelineSeverity.WARNING
    return PlanningTimelineSeverity.ERROR


def _runtime_severity(status):
    if status.value == "ready":
        return PlanningTimelineSeverity.SUCCESS
    if status.value in {"partial", "stale"}:
        return PlanningTimelineSeverity.WARNING
    return PlanningTimelineSeverity.ERROR


def _readiness_severity(status: PlanningReadinessStatus):
    if status is PlanningReadinessStatus.READY:
        return PlanningTimelineSeverity.SUCCESS
    if status in {
        PlanningReadinessStatus.WARNING,
        PlanningReadinessStatus.PARTIAL,
        PlanningReadinessStatus.STALE,
    }:
        return PlanningTimelineSeverity.WARNING
    if status is PlanningReadinessStatus.BLOCKED:
        return PlanningTimelineSeverity.CRITICAL
    return PlanningTimelineSeverity.ERROR


class PlanningTimelineEngine:
    def __init__(self, formatter: PlanningTimelineFormatter) -> None:
        self._formatter = formatter

    def build(
        self,
        *,
        readiness: PlanningReadinessResult,
        conflicts: PlanningConflictReport,
        composition: PlanningTimelineCompositionReport,
        evaluated_at: datetime,
    ) -> PlanningTimelineResult:
        unit = readiness.operational_unit
        planning_date = readiness.planning_date
        events = []
        for label, category, snapshot in (
            ("Workforce", PlanningTimelineCategory.WORKFORCE, composition.workforce),
            ("Fleet", PlanningTimelineCategory.FLEET, composition.fleet),
        ):
            if snapshot is None:
                continue
            metadata = snapshot.contract.metadata
            status = snapshot.validation.status
            events.append(
                self._formatter.format(
                    timestamp=metadata.source.produced_at,
                    category=category,
                    severity=_snapshot_severity(status),
                    title=f"{label} aggiornato",
                    description=(
                        f"Snapshot {label} acquisito con stato {status.value}."
                    ),
                    status=status.value.upper(),
                    source=label.casefold(),
                    operational_unit=unit,
                    planning_date=planning_date,
                    reference=snapshot.snapshot_id,
                    related_readiness=readiness.status.value,
                    metadata={
                        "version": metadata.version.value,
                        "producer": metadata.source.producer,
                    },
                )
            )
        if readiness.envelope_version:
            events.append(
                self._formatter.format(
                    timestamp=composition.timestamp,
                    category=PlanningTimelineCategory.IMPORT,
                    severity=PlanningTimelineSeverity.SUCCESS,
                    title="Planning Input creato",
                    description=(
                        "Workforce e Fleet sono stati composti nel Planning Input."
                    ),
                    status="CREATED",
                    source="planning-input",
                    operational_unit=unit,
                    planning_date=planning_date,
                    reference=readiness.envelope_version,
                    related_readiness=readiness.status.value,
                    metadata={"version": readiness.envelope_version},
                )
            )
        events.append(
            self._formatter.format(
                timestamp=composition.timestamp,
                category=PlanningTimelineCategory.RUNTIME,
                severity=_runtime_severity(composition.status),
                title="Runtime Composition completata",
                description=(
                    "Il Runtime ha verificato scope, sorgenti e compatibilita degli input."
                ),
                status=composition.status.value.upper(),
                source="runtime-composition",
                operational_unit=unit,
                planning_date=planning_date,
                reference=(
                    f"runtime:{unit.external_identifier}:"
                    f"{planning_date.isoformat()}"
                ),
                related_readiness=readiness.status.value,
                metadata={
                    "compatible": composition.compatibility.compatible,
                    "legacy_flow_active": composition.legacy_flow_active,
                },
            )
        )
        events.append(
            self._formatter.format(
                timestamp=readiness.evaluated_at,
                category=PlanningTimelineCategory.READINESS,
                severity=_readiness_severity(readiness.status),
                title="Planning Readiness completata",
                description=readiness.rationale,
                status=readiness.status.value,
                source="planning-readiness",
                operational_unit=unit,
                planning_date=planning_date,
                reference=readiness.envelope_version,
                related_readiness=readiness.status.value,
                metadata={"score": readiness.score.value},
            )
        )
        if conflicts.total_conflicts:
            events.append(
                self._formatter.format(
                    timestamp=conflicts.timestamp,
                    category=PlanningTimelineCategory.CONFLICT,
                    severity=(
                        PlanningTimelineSeverity.CRITICAL
                        if conflicts.total_blocking
                        else PlanningTimelineSeverity.WARNING
                    ),
                    title="Conflitti operativi rilevati",
                    description=(
                        f"Rilevati {conflicts.total_conflicts} conflitti, "
                        f"di cui {conflicts.total_blocking} bloccanti."
                    ),
                    status=(
                        "BLOCKING" if conflicts.total_blocking else "WARNING"
                    ),
                    source="conflict-review",
                    operational_unit=unit,
                    planning_date=planning_date,
                    reference=conflicts.planning_version,
                    related_conflicts=tuple(
                        item.id for item in conflicts.conflicts
                    ),
                    related_readiness=readiness.status.value,
                    metadata={
                        "total": conflicts.total_conflicts,
                        "blocking": conflicts.total_blocking,
                    },
                )
            )
        if readiness.legacy_flow_active:
            events.append(
                self._formatter.format(
                    timestamp=evaluated_at,
                    category=PlanningTimelineCategory.LEGACY,
                    severity=PlanningTimelineSeverity.INFO,
                    title="Planning legacy ancora attivo",
                    description=(
                        "Il Planning Engine continua a usare il flusso legacy."
                    ),
                    status="ACTIVE",
                    source="planning-legacy",
                    operational_unit=unit,
                    planning_date=planning_date,
                    reference="legacy-planning",
                    related_readiness=readiness.status.value,
                )
            )
        ordered = sort_planning_timeline_events(tuple(events))
        report = PlanningTimelineReport(
            event_count=len(ordered),
            last_updated=ordered[0].timestamp if ordered else None,
            current_status=readiness.status.value,
            groups=group_planning_timeline_events(
                ordered,
                evaluated_at=evaluated_at,
            ),
            events=ordered,
        )
        return PlanningTimelineResult(report=report)
