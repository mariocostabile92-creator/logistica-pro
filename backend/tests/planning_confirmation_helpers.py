from datetime import UTC, datetime, timedelta

from app.domain.core_language import OperationalUnit
from app.domain.planning_confirmation import (
    PlanningConfirmationPolicy,
    PlanningConfirmationScope,
    PlanningConfirmationService,
    PlanningConfirmationValidationContext,
    PlanningConfirmationValidator,
)
from app.domain.planning_conflicts import (
    PlanningConflictEngine,
    PlanningConflictEvaluator,
    PlanningConflictFormatter,
)
from app.domain.planning_drafts import (
    PlanningDraftMetadata,
    PlanningDraftScope,
    PlanningDraftService,
)
from app.domain.planning_readiness import PlanningReadinessEvaluator
from app.plugins.fleet.application.planning_input_producer import (
    build_fleet_planning_input_snapshot,
)
from app.plugins.fleet.domain.models import Asset
from app.plugins.workforce.application.planning_input_producer import (
    build_workforce_planning_input_snapshot,
)
from app.plugins.workforce.domain.models import (
    WorkforceDayStatus,
    WorkforceMember,
    WorkforceRequirement,
    WorkforceValueOrigin,
)
from app.repositories.planning_confirmation_repository import (
    SqlPlanningConfirmationRepository,
)
from app.repositories.planning_draft_repository import (
    SqlPlanningDraftRepository,
)
from app.runtime.planning_confirmation import PlanningConfirmationRuntime
from app.runtime.planning_drafts import PlanningDraftRuntime
from app.runtime.planning_inputs import PlanningInputRuntimeService
from app.runtime.planning_readiness import PlanningReadinessService


NOW = datetime.now(UTC).replace(microsecond=0)
RECENT = NOW - timedelta(minutes=15)
OPERATION_DATE = NOW.date()
UNIT = OperationalUnit(external_identifier="unit-a", name="Unit A")
ORGANIZATION_ID = "organization-one"
SCOPE = PlanningConfirmationScope(
    organization_id=ORGANIZATION_ID,
    operational_unit=UNIT,
    planning_date=OPERATION_DATE,
)


class Identifiers:
    def __init__(self) -> None:
        self._value = 0

    def __call__(self) -> str:
        self._value += 1
        return f"id-{self._value}"


def _iso(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


def _workforce_snapshot(**request):
    member = WorkforceMember(
        workforce_member_id=1,
        external_identifier="human-001",
        display_name="Resource One",
        role="courier",
        capabilities=["license-b"],
        source_reference="synthetic:human-001",
        created_at=_iso(RECENT),
        updated_at=_iso(RECENT),
    )
    status = WorkforceDayStatus(
        status_id=1,
        workforce_member_id=1,
        date=OPERATION_DATE.isoformat(),
        status_code="scheduled",
        availability=True,
        shift_code="morning",
        start_time="07:00",
        end_time="15:00",
        source_reference="synthetic:status-001",
        observed_or_confirmed=WorkforceValueOrigin.IMPORTED,
        updated_at=_iso(RECENT),
    )
    requirement = WorkforceRequirement(
        requirement_id=1,
        date=OPERATION_DATE.isoformat(),
        operational_unit_id=UNIT.external_identifier,
        required_resources=1,
        required_capabilities=["license-b"],
        source="synthetic",
        version=1,
    )
    return build_workforce_planning_input_snapshot(
        organization_id=request["organization_id"],
        operational_unit=request["operational_unit"],
        operation_date=request["operation_date"],
        members=[member],
        statuses=[status],
        requirements=[requirement],
        assessed_at=request["assessed_at"],
        freshness_ttl=request["freshness_ttl"],
    )


def _fleet_snapshot(**request):
    asset = Asset(
        id=1,
        external_identifier="asset-001",
        plate="QA00001",
        category="van",
        status="active",
        availability="available",
        capabilities=["electric"],
        created_at=_iso(RECENT),
        updated_at=_iso(RECENT),
    )
    return build_fleet_planning_input_snapshot(
        organization_id=request["organization_id"],
        operational_unit=request["operational_unit"],
        operation_date=request["operation_date"],
        assets=[asset],
        assessed_at=request["assessed_at"],
        freshness_ttl=request["freshness_ttl"],
    )


def readiness_service() -> PlanningReadinessService:
    runtime = PlanningInputRuntimeService(
        workforce_producer=_workforce_snapshot,
        fleet_producer=_fleet_snapshot,
        workforce_freshness_ttl=timedelta(days=1),
        fleet_freshness_ttl=timedelta(days=1),
    )
    return PlanningReadinessService(
        composition_provider=runtime,
        evaluator=PlanningReadinessEvaluator(),
    )


def conflict_engine() -> PlanningConflictEngine:
    return PlanningConflictEngine(
        PlanningConflictEvaluator(PlanningConflictFormatter())
    )


def draft_service() -> PlanningDraftService:
    return PlanningDraftService(
        repository=SqlPlanningDraftRepository(),
        clock=lambda: NOW,
        identifier_factory=Identifiers(),
    )


def create_draft(service: PlanningDraftService, *, saved: bool = True):
    created = service.create(
        scope=PlanningDraftScope(
            organization_id=ORGANIZATION_ID,
            operational_unit=UNIT,
            planning_date=OPERATION_DATE,
        ),
        metadata=PlanningDraftMetadata(
            name="Draft confermabile",
            note="Solo metadati.",
        ),
        actor="draft-author",
    )
    if not saved:
        return created.draft
    return service.save(
        draft_id=created.draft.draft_id,
        expected_version=created.draft.version.number,
        actor="draft-author",
    ).draft


def confirmation_service() -> PlanningConfirmationService:
    return PlanningConfirmationService(
        repository=SqlPlanningConfirmationRepository(),
        validator=PlanningConfirmationValidator(
            PlanningConfirmationPolicy()
        ),
        clock=lambda: NOW + timedelta(minutes=5),
        identifier_factory=Identifiers(),
    )


def confirmation_context(
    draft,
    *,
    service: PlanningConfirmationService | None = None,
) -> PlanningConfirmationValidationContext:
    readiness_context = readiness_service().evaluate_with_context(
        organization_id=ORGANIZATION_ID,
        operational_unit=UNIT,
        operation_date=OPERATION_DATE,
        evaluated_at=NOW,
    )
    conflicts = conflict_engine().review(
        readiness=readiness_context.result,
        envelope=readiness_context.envelope,
    )
    return PlanningConfirmationValidationContext(
        scope=SCOPE,
        requested_draft_id=draft.draft_id if draft else None,
        requested_draft_version=draft.version.number if draft else None,
        draft=draft,
        readiness=readiness_context.result,
        conflicts=conflicts,
        envelope=readiness_context.envelope,
        runtime_status=readiness_context.composition_report.status.value,
        runtime_compatible=(
            readiness_context.composition_report.compatibility.compatible
        ),
        active_confirmation=(service.get_current(SCOPE) if service else None),
        evaluated_at=NOW,
    )


def confirmation_runtime():
    drafts = draft_service()
    draft = create_draft(drafts)
    runtime = PlanningConfirmationRuntime(
        service=confirmation_service(),
        draft_provider=PlanningDraftRuntime(
            service=drafts,
            actor="draft-author",
        ),
        readiness_provider=readiness_service(),
        conflict_reviewer=conflict_engine(),
        actor="qa-operator",
    )
    return runtime, draft
