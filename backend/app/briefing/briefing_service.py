import json
from dataclasses import dataclass
from hashlib import sha256
from threading import Lock

from app.briefing import repository
from app.briefing.issue_collectors import (
    build_ranked_sections,
    collect_issue_candidates,
)
from app.briefing.models import (
    BRIEFING_CONTRACT_VERSION,
    AttentionLevel,
    BriefingMetrics,
    BriefingSeverity,
    BriefingStatus,
    CapacitySnapshot,
    DailyOperationsBriefing,
    ReadinessSnapshot,
    SourceReference,
    SourceType,
)
from app.briefing.prioritization import AttentionInputs, attention_level
from app.briefing.plugin_sections import merge_plugin_sections
from app.core.configuration.models import Configuration, ConfigurationScope
from app.core.configuration.service import get_current_configuration
from app.domain.operations_engine import OperationsDashboard
from app.domain.planning_models import PlanningBundle
from app.plugins.fleet.application.asset_service import list_assets
from app.plugins.fleet.application.sync_service import briefing_snapshot as fleet_briefing_snapshot
from app.plugins.fleet.domain.models import Asset
from app.plugins.fleet.domain.sync_models import FleetBriefingSnapshot
from app.plugins.workforce.application.workforce_service import briefing_snapshot as workforce_briefing_snapshot
from app.plugins.workforce.bootstrap import workforce_plugin_enabled
from app.plugins.workforce.domain.models import WorkforceBriefingSnapshot
from app.repositories.import_repository import get_import
from app.repositories.operations_repository import (
    get_latest_operation_snapshot,
)
from app.services.planning_generation_service import (
    PlanningNotFoundError,
    get_latest_planning_bundle,
    get_planning_bundle,
)
from app.utils.date_utils import utc_now_iso


_GENERATION_LOCK = Lock()


@dataclass(frozen=True)
class BriefingSourceContext:
    bundle: PlanningBundle
    dashboard: OperationsDashboard | None
    dashboard_snapshot_id: int | None
    assets: list[Asset]
    configuration: Configuration
    is_demo: bool
    workforce: WorkforceBriefingSnapshot | None
    fleet: FleetBriefingSnapshot


def _unavailable(
    *,
    message: str,
    limitation: str,
    bundle: PlanningBundle | None = None,
) -> DailyOperationsBriefing:
    return DailyOperationsBriefing(
        operation_date=(
            bundle.planning.operation_date if bundle else None
        ),
        planning_id=bundle.planning.id if bundle else None,
        planning_version=bundle.planning.version if bundle else None,
        status=BriefingStatus.UNAVAILABLE,
        executive_summary=message,
        attention_level=AttentionLevel.UNAVAILABLE,
        attention_reason=limitation,
        readiness_snapshot=ReadinessSnapshot(
            available=False,
            reasons=[limitation],
        ),
        capacity_snapshot=CapacitySnapshot(available=False),
        limitations=[limitation],
    )


def _load_bundle(planning_id: int | None) -> PlanningBundle | None:
    try:
        if planning_id is None:
            return get_latest_planning_bundle()
        return get_planning_bundle(planning_id)
    except PlanningNotFoundError:
        if planning_id is not None:
            raise
        return None


def _matching_dashboard(
    bundle: PlanningBundle,
) -> tuple[OperationsDashboard | None, int | None]:
    snapshot = get_latest_operation_snapshot()
    if not snapshot:
        return None, None
    planning = bundle.planning
    if (
        int(snapshot["planning_import_id"])
        != planning.source_planning_import_id
        or int(snapshot["fleet_import_id"])
        != planning.source_fleet_import_id
        or int(snapshot["reserve_threshold"])
        != planning.reserve_threshold
    ):
        return None, None
    return (
        OperationsDashboard.model_validate(snapshot["payload"]),
        int(snapshot["id"]),
    )


def _is_demo_bundle(bundle: PlanningBundle) -> bool:
    planning_import = get_import(
        bundle.planning.source_planning_import_id,
        "planning",
    )
    fleet_import = get_import(
        bundle.planning.source_fleet_import_id,
        "fleet",
    )
    return bool(
        planning_import
        and fleet_import
        and str(planning_import["original_filename"]).startswith("DEMO__")
        and str(fleet_import["original_filename"]).startswith("DEMO__")
    )


def _load_context(
    planning_id: int | None = None,
) -> BriefingSourceContext | None:
    bundle = _load_bundle(planning_id)
    if not bundle:
        return None
    dashboard, snapshot_id = _matching_dashboard(bundle)
    operation_date = bundle.planning.operation_date
    return BriefingSourceContext(
        bundle=bundle,
        dashboard=dashboard,
        dashboard_snapshot_id=snapshot_id,
        assets=list_assets(),
        configuration=get_current_configuration(
            ConfigurationScope(organization_id="default")
        ),
        is_demo=_is_demo_bundle(bundle),
        workforce=(
            workforce_briefing_snapshot(operation_date)
            if workforce_plugin_enabled()
            else None
        ),
        fleet=fleet_briefing_snapshot(operation_date),
    )


def _canonical_dashboard(
    dashboard: OperationsDashboard | None,
) -> dict[str, object] | None:
    if not dashboard:
        return None
    return dashboard.model_dump(
        mode="json",
        exclude={"analysis_id", "generated_at"},
    )


def source_fingerprint(context: BriefingSourceContext) -> str:
    canonical_sources = {
        "contract_version": BRIEFING_CONTRACT_VERSION,
        "planning": context.bundle.model_dump(mode="json"),
        "operations": _canonical_dashboard(context.dashboard),
        "fleet_assets": [
            item.model_dump(mode="json") for item in context.assets
        ],
        "configuration": context.configuration.model_dump(mode="json"),
        "is_demo": context.is_demo,
        "workforce": (
            context.workforce.model_dump(mode="json")
            if context.workforce else None
        ),
        "fleet_registry": context.fleet.model_dump(mode="json"),
    }
    serialized = json.dumps(
        canonical_sources,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return sha256(serialized.encode("utf-8")).hexdigest()


def _readiness_snapshot(
    context: BriefingSourceContext,
) -> ReadinessSnapshot:
    dashboard = context.dashboard
    if not dashboard:
        return ReadinessSnapshot(
            available=False,
            reasons=[
                "Nessuno snapshot Readiness compatibile è disponibile."
            ],
        )
    readiness = dashboard.readiness
    return ReadinessSnapshot(
        available=True,
        level=readiness.status.value,
        risk_level=readiness.risk_level.value,
        can_start_all_tasks=readiness.can_start_all_routes,
        blocking_issues=readiness.critical_issues,
        warnings=readiness.warning_issues,
        reasons=readiness.reasons,
        source_reference=SourceReference(
            source_type=SourceType.READINESS,
            source_id=(
                f"operation-snapshot:{context.dashboard_snapshot_id}"
            ),
            source_version=dashboard.generated_at,
            field_path="readiness",
            label="Readiness operativa",
        ),
    )


def _capacity_snapshot(
    context: BriefingSourceContext,
) -> CapacitySnapshot:
    bundle = context.bundle
    version = str(bundle.planning.version)
    unit_references = [
        SourceReference(
            source_type=SourceType.CAPACITY,
            source_id=(
                f"{bundle.planning.id}:capacity:{unit.station}"
            ),
            source_version=version,
            field_path="station_capacity",
            label=f"Capacità {unit.station}",
        )
        for unit in sorted(
            bundle.station_capacity,
            key=lambda item: item.station,
        )
    ]
    under_pressure = sorted(
        unit.station
        for unit in bundle.station_capacity
        if unit.operational_margin < unit.reserve_threshold
    )
    if context.dashboard:
        capacity = context.dashboard.capacity
        references = [
            SourceReference(
                source_type=SourceType.CAPACITY,
                source_id=(
                    f"operation-snapshot:"
                    f"{context.dashboard_snapshot_id}"
                ),
                source_version=context.dashboard.generated_at,
                field_path="capacity",
                label="Capacità operativa aggregata",
            ),
            *unit_references,
        ]
        return CapacitySnapshot(
            available=True,
            demand=capacity.routes,
            available_capacity=capacity.operational_vehicles,
            margin=capacity.operational_margin,
            reserve_threshold=context.dashboard.readiness.reserve_threshold,
            operational_units_under_pressure=under_pressure,
            source_references=references,
        )
    if not bundle.station_capacity:
        return CapacitySnapshot(available=False)
    return CapacitySnapshot(
        available=True,
        demand=sum(
            item.routes_total for item in bundle.station_capacity
        ),
        available_capacity=sum(
            item.operational_vehicles
            for item in bundle.station_capacity
        ),
        margin=sum(
            item.operational_margin
            for item in bundle.station_capacity
        ),
        reserve_threshold=sum(
            item.reserve_threshold
            for item in bundle.station_capacity
        ),
        operational_units_under_pressure=under_pressure,
        source_references=unit_references,
    )


def _limitations(context: BriefingSourceContext) -> list[str]:
    limitations = [
        (
            "La compatibilità tra capability richieste e disponibili non "
            "è esposta come esito tipizzato dal Planning corrente; il "
            "briefing non la ricostruisce."
        )
    ]
    if not context.dashboard:
        limitations.append(
            "Nessuno snapshot Readiness compatibile è disponibile; il "
            "briefing non ha ricalcolato Readiness o Capacity."
        )
    if not context.assets:
        limitations.append(
            "Il Fleet Plugin non espone Asset per il Planning analizzato."
        )
    if workforce_plugin_enabled() and not context.workforce:
        limitations.append(
            "Nessuna disponibilita Workforce e disponibile per la data operativa."
        )
    return limitations


def _deduplicate_references(
    references: list[SourceReference],
) -> list[SourceReference]:
    unique: dict[tuple[str, str, str, str], SourceReference] = {}
    for reference in references:
        key = (
            reference.source_type.value,
            reference.source_id,
            reference.source_version or "",
            reference.field_path,
        )
        unique[key] = reference
    return [unique[key] for key in sorted(unique)[:1000]]


def _all_source_references(
    context: BriefingSourceContext,
    sections,
    readiness: ReadinessSnapshot,
    capacity: CapacitySnapshot,
) -> list[SourceReference]:
    bundle = context.bundle
    references = [
        SourceReference(
            source_type=SourceType.PLANNING,
            source_id=str(bundle.planning.id),
            source_version=str(bundle.planning.version),
            field_path="planning",
            label="Planning analizzato",
        ),
        SourceReference(
            source_type=SourceType.CONFIGURATION,
            source_id=context.configuration.configuration_id,
            source_version=str(context.configuration.version.number),
            field_path="sections",
            label="Configurazione effettiva",
        ),
        *capacity.source_references,
    ]
    if readiness.source_reference:
        references.append(readiness.source_reference)
    for section in sections:
        references.extend(section.source_references)
    return _deduplicate_references(references)


def _metrics(sections) -> BriefingMetrics:
    return BriefingMetrics(
        critical_items=sum(
            item.severity
            in {BriefingSeverity.BLOCKER, BriefingSeverity.CRITICAL}
            for item in sections
        ),
        attention_items=sum(
            item.severity
            in {BriefingSeverity.HIGH, BriefingSeverity.MEDIUM}
            for item in sections
        ),
        information_items=sum(
            item.severity
            in {BriefingSeverity.LOW, BriefingSeverity.INFORMATION}
            for item in sections
        ),
        recommended_actions=sum(
            item.recommendation is not None for item in sections
        ),
    )


def _executive_summary(
    level: AttentionLevel,
    metrics: BriefingMetrics,
    sections,
) -> str:
    if level == AttentionLevel.CRITICAL:
        return (
            "Il piano richiede una decisione prima dell'avvio: "
            f"{metrics.critical_items} elementi critici e "
            f"{metrics.attention_items} elementi di attenzione."
        )
    if level == AttentionLevel.STABLE:
        return (
            "Il piano non presenta condizioni bloccanti e rispetta il "
            "margine operativo configurato."
        )
    themes: list[str] = []
    issue_codes = {item.issue_code for item in sections}
    if any(code.startswith("READINESS_") for code in issue_codes):
        themes.append("Readiness")
    if issue_codes.intersection(
        {"RESERVE_MARGIN_LOW", "RESERVE_ASSET_IN_USE"}
    ):
        themes.append("riserva Asset")
    if "HUMAN_RESOURCE_SUBSTITUTED" in issue_codes:
        themes.append("disponibilità Human Resource")
    if any(
        item.category.value == "assets" for item in sections
    ) and "riserva Asset" not in themes:
        themes.append("disponibilità Asset")
    if not themes:
        themes.append("warning operativi")
    if len(themes) == 1:
        focus = themes[0]
    else:
        focus = ", ".join(themes[:-1]) + f" e {themes[-1]}"
    return (
        "Il piano è eseguibile, ma richiede attenzione su "
        f"{focus}."
    )


def get_latest_daily_briefing() -> DailyOperationsBriefing:
    context = _load_context()
    if not context:
        return _unavailable(
            message=(
                "Il briefing sarà disponibile dopo la creazione del "
                "primo planning."
            ),
            limitation="Nessun Planning disponibile.",
        )
    fingerprint = source_fingerprint(context)
    existing = repository.get_by_fingerprint(fingerprint)
    if existing:
        return existing
    return _unavailable(
        message=(
            "Il briefing del Planning corrente non è ancora stato "
            "generato."
        ),
        limitation=(
            "Le fonti correnti non corrispondono a un briefing "
            "persistito."
        ),
        bundle=context.bundle,
    )


def generate_daily_briefing(
    planning_id: int | None = None,
) -> DailyOperationsBriefing:
    with _GENERATION_LOCK:
        context = _load_context(planning_id)
        if not context:
            return _unavailable(
                message=(
                    "Il briefing sarà disponibile dopo la creazione del "
                    "primo planning."
                ),
                limitation="Nessun Planning disponibile.",
            )
        fingerprint = source_fingerprint(context)
        existing = repository.get_by_fingerprint(fingerprint)
        if existing:
            return existing

        bundle = context.bundle
        planning_id_value = int(bundle.planning.id)
        sections = build_ranked_sections(
            collect_issue_candidates(
                bundle=bundle,
                dashboard=context.dashboard,
                dashboard_snapshot_id=context.dashboard_snapshot_id,
                assets=context.assets,
            )
        )
        sections = merge_plugin_sections(
            sections,
            context.workforce,
            context.fleet,
        )
        readiness = _readiness_snapshot(context)
        capacity = _capacity_snapshot(context)
        level, reason = attention_level(
            AttentionInputs(
                planning_status=bundle.planning.status.value,
                uncovered_tasks=len(bundle.unassigned_routes),
                readiness_level=readiness.level,
                capacity_margin=capacity.margin,
                reserve_threshold=capacity.reserve_threshold,
                severities=tuple(
                    item.severity for item in sections
                ),
            )
        )
        metrics = _metrics(sections)
        operational_unit_ids = sorted(
            {item.station for item in bundle.station_capacity}
        )
        briefing = DailyOperationsBriefing(
            briefing_id=f"briefing-{fingerprint[:24]}",
            briefing_revision=repository.next_revision(
                planning_id_value
            ),
            fingerprint=fingerprint,
            generated_at=utc_now_iso(),
            operation_date=bundle.planning.operation_date,
            planning_id=planning_id_value,
            planning_version=bundle.planning.version,
            configuration_version=context.configuration.version.number,
            organization_id=(
                context.configuration.metadata.requested_scope.organization_id
            ),
            operational_unit_ids=operational_unit_ids,
            status=BriefingStatus.AVAILABLE,
            executive_summary=_executive_summary(
                level,
                metrics,
                sections,
            ),
            attention_level=level,
            attention_reason=reason,
            readiness_snapshot=readiness,
            capacity_snapshot=capacity,
            metrics=metrics,
            sections=sections,
            source_references=_all_source_references(
                context,
                sections,
                readiness,
                capacity,
            ),
            limitations=_limitations(context),
            is_demo=context.is_demo,
        )
        return repository.save(briefing)
