from dataclasses import dataclass, field
from datetime import date, timedelta
from hashlib import sha256

from app.briefing.models import (
    ActionLink,
    BriefingCategory,
    BriefingFact,
    BriefingSection,
    BriefingSeverity,
    FactProvenance,
    SourceReference,
    SourceType,
    WorkspaceTarget,
)
from app.briefing.prioritization import (
    priority_score,
    ranking_explanation,
)
from app.briefing.recommendations import recommendation_for
from app.domain.operations_engine import OperationsDashboard
from app.domain.planning_models import PlanningBundle
from app.plugins.fleet.domain.models import Asset


@dataclass
class IssueCandidate:
    issue_code: str
    entity_key: str
    title: str
    category: BriefingCategory
    severity: BriefingSeverity
    urgency: int
    operational_impact: int
    summary: str
    rationale: str
    facts: list[BriefingFact] = field(default_factory=list)
    source_references: list[SourceReference] = field(default_factory=list)
    alternatives: list[str] = field(default_factory=list)
    confidence: float | None = None
    entity_type: str | None = None
    entity_id: str | None = None
    fallback_recommendation: str | None = None


def _source_reference(
    source_type: SourceType,
    source_id: str,
    source_version: str | None,
    field_path: str,
    label: str,
) -> SourceReference:
    return SourceReference(
        source_type=source_type,
        source_id=source_id,
        source_version=source_version,
        field_path=field_path,
        label=label,
    )


def _fact(
    *,
    fact_id: str,
    fact_type: str,
    label: str,
    value,
    source_type: SourceType,
    source_id: str,
    source_version: str | None,
    observed_at: str | None,
    provenance: FactProvenance,
) -> BriefingFact:
    return BriefingFact(
        fact_id=fact_id,
        fact_type=fact_type,
        label=label,
        value=value,
        source_type=source_type,
        source_id=source_id,
        source_version=source_version,
        observed_at=observed_at,
        provenance=provenance,
    )


def _stable_section_id(issue_code: str, entity_key: str) -> str:
    digest = sha256(entity_key.encode("utf-8")).hexdigest()[:12]
    return f"{issue_code.casefold().replace('_', '-')}-{digest}"


def _deduplicate_references(
    references: list[SourceReference],
) -> list[SourceReference]:
    unique: dict[tuple[str, str, str | None, str], SourceReference] = {}
    for reference in references:
        key = (
            reference.source_type.value,
            reference.source_id,
            reference.source_version,
            reference.field_path,
        )
        unique[key] = reference
    return [
        unique[key]
        for key in sorted(
            unique,
            key=lambda item: (
                item[0],
                item[1],
                item[2] or "",
                item[3],
            ),
        )
    ]


def _severity_from_source(value: str) -> BriefingSeverity:
    return {
        "critical": BriefingSeverity.CRITICAL,
        "warning": BriefingSeverity.MEDIUM,
        "info": BriefingSeverity.INFORMATION,
    }.get(value, BriefingSeverity.LOW)


def _collect_uncovered_tasks(bundle: PlanningBundle) -> list[IssueCandidate]:
    planning_id = str(bundle.planning.id)
    version = str(bundle.planning.version)
    observed_at = bundle.planning.updated_at
    candidates: list[IssueCandidate] = []
    for task_id in sorted(bundle.unassigned_routes):
        reference = _source_reference(
            SourceType.PLANNING,
            planning_id,
            version,
            "unassigned_tasks",
            "Task senza Assignment completa",
        )
        candidates.append(
            IssueCandidate(
                issue_code="TASK_UNCOVERED",
                entity_key=task_id,
                title=f"Task {task_id} non coperto",
                category=BriefingCategory.CRITICAL_ATTENTION,
                severity=BriefingSeverity.BLOCKER,
                urgency=4,
                operational_impact=4,
                summary=(
                    "Il Planning indica che il Task non dispone di tutte "
                    "le risorse necessarie."
                ),
                rationale=(
                    "Un Task scoperto impedisce di considerare completa "
                    "l'esecuzione del piano."
                ),
                facts=[
                    _fact(
                        fact_id=f"uncovered-task-{task_id}",
                        fact_type="task_coverage",
                        label="Copertura Task",
                        value="uncovered",
                        source_type=SourceType.PLANNING,
                        source_id=planning_id,
                        source_version=version,
                        observed_at=observed_at,
                        provenance=FactProvenance.OBSERVED,
                    )
                ],
                source_references=[reference],
                entity_type="task",
                entity_id=task_id,
            )
        )
    return candidates


def _collect_capacity(bundle: PlanningBundle) -> list[IssueCandidate]:
    planning_id = str(bundle.planning.id)
    version = str(bundle.planning.version)
    candidates: list[IssueCandidate] = []
    for unit in sorted(
        bundle.station_capacity,
        key=lambda item: item.station,
    ):
        if unit.operational_margin >= unit.reserve_threshold:
            continue
        shortage = unit.operational_margin < 0
        issue_code = (
            "CAPACITY_SHORTAGE" if shortage else "RESERVE_MARGIN_LOW"
        )
        severity = (
            BriefingSeverity.BLOCKER
            if shortage
            else BriefingSeverity.HIGH
        )
        unit_id = unit.station
        source_id = f"{planning_id}:capacity:{unit_id}"
        references = [
            _source_reference(
                SourceType.CAPACITY,
                source_id,
                version,
                field_path,
                label,
            )
            for field_path, label in (
                ("routes_total", "Domanda"),
                ("operational_vehicles", "Capacità disponibile"),
                ("operational_margin", "Margine operativo"),
                ("reserve_threshold", "Soglia di riserva"),
            )
        ]
        candidates.append(
            IssueCandidate(
                issue_code=issue_code,
                entity_key=unit_id,
                title=(
                    f"Capacità insufficiente in {unit_id}"
                    if shortage
                    else f"Margine di riserva ridotto in {unit_id}"
                ),
                category=(
                    BriefingCategory.CRITICAL_ATTENTION
                    if shortage
                    else BriefingCategory.CAPACITY
                ),
                severity=severity,
                urgency=4 if shortage else 3,
                operational_impact=4 if shortage else 3,
                summary=(
                    f"Domanda {unit.routes_total}, capacità disponibile "
                    f"{unit.operational_vehicles}, margine "
                    f"{unit.operational_margin}, soglia "
                    f"{unit.reserve_threshold}."
                ),
                rationale=(
                    "La capacità non copre la domanda."
                    if shortage
                    else "Il margine disponibile è inferiore alla soglia configurata."
                ),
                facts=[
                    _fact(
                        fact_id=f"{issue_code.casefold()}-{unit_id}-margin",
                        fact_type="capacity_margin",
                        label="Margine operativo",
                        value=unit.operational_margin,
                        source_type=SourceType.CAPACITY,
                        source_id=source_id,
                        source_version=version,
                        observed_at=bundle.planning.updated_at,
                        provenance=FactProvenance.DERIVED,
                    ),
                    _fact(
                        fact_id=f"{issue_code.casefold()}-{unit_id}-threshold",
                        fact_type="reserve_threshold",
                        label="Soglia di riserva",
                        value=unit.reserve_threshold,
                        source_type=SourceType.CONFIGURATION,
                        source_id=f"planning:{planning_id}",
                        source_version=version,
                        observed_at=bundle.planning.updated_at,
                        provenance=FactProvenance.CONFIGURED,
                    ),
                ],
                source_references=references,
                entity_type="operational_unit",
                entity_id=unit_id,
            )
        )
    return candidates


def _readiness_candidate(
    dashboard: OperationsDashboard | None,
    snapshot_id: int | None,
) -> list[IssueCandidate]:
    if not dashboard or dashboard.readiness.status.value == "green":
        return []
    readiness = dashboard.readiness
    critical = readiness.status.value == "red"
    issue_code = (
        "READINESS_CRITICAL" if critical else "READINESS_ATTENTION"
    )
    source_id = f"operation-snapshot:{snapshot_id}"
    version = dashboard.generated_at
    reference = _source_reference(
        SourceType.READINESS,
        source_id,
        version,
        "readiness",
        "Readiness operativa",
    )
    return [
        IssueCandidate(
            issue_code=issue_code,
            entity_key=source_id,
            title=(
                "Readiness critica"
                if critical
                else "Readiness da verificare"
            ),
            category=(
                BriefingCategory.CRITICAL_ATTENTION
                if critical
                else BriefingCategory.READINESS
            ),
            severity=(
                BriefingSeverity.CRITICAL
                if critical
                else BriefingSeverity.HIGH
            ),
            urgency=4 if critical else 3,
            operational_impact=4 if critical else 3,
            summary=" ".join(readiness.reasons),
            rationale=(
                "La Readiness già calcolata segnala condizioni bloccanti."
                if critical
                else "La Readiness già calcolata segnala warning da confermare."
            ),
            facts=[
                _fact(
                    fact_id=f"{issue_code.casefold()}-level",
                    fact_type="readiness_level",
                    label="Livello Readiness",
                    value=readiness.status.value,
                    source_type=SourceType.READINESS,
                    source_id=source_id,
                    source_version=version,
                    observed_at=dashboard.generated_at,
                    provenance=FactProvenance.DERIVED,
                )
            ],
            source_references=[reference],
        )
    ]


def _event_references(
    bundle: PlanningBundle,
    event_type: str,
) -> list[SourceReference]:
    references: list[SourceReference] = []
    for event in bundle.history.get("events", []):
        if str(event.get("event_type")) != event_type:
            continue
        event_id = str(event.get("id") or "unknown")
        references.append(
            _source_reference(
                SourceType.PLANNING_EVENT,
                event_id,
                str(event.get("planning_version") or bundle.planning.version),
                "event_type",
                "Evento operativo applicato",
            )
        )
    return references


def _collect_assignments(bundle: PlanningBundle) -> list[IssueCandidate]:
    candidates: list[IssueCandidate] = []
    planning_version = str(bundle.planning.version)
    absence_references = _event_references(bundle, "driver_absent")
    alternative_assignments = []
    for assignment in sorted(
        bundle.assignments,
        key=lambda item: item.route_id,
    ):
        assignment_id = str(assignment.id or assignment.route_id)
        assignment_ref = _source_reference(
            SourceType.ASSIGNMENT,
            assignment_id,
            planning_version,
            "warnings",
            "Warning Assignment",
        )
        for warning in sorted(set(assignment.warnings)):
            if warning == "DRIVER_ABSENT_REPLACED":
                issue_code = "HUMAN_RESOURCE_SUBSTITUTED"
                category = BriefingCategory.HUMAN_RESOURCES
                severity = BriefingSeverity.HIGH
                title = (
                    f"Sostituzione Human Resource per Task "
                    f"{assignment.route_id}"
                )
                rationale = (
                    "La copertura è stata ripristinata, ma la sostituzione "
                    "richiede conferma umana."
                )
            elif warning == "RESERVE_VEHICLE_USED":
                issue_code = "RESERVE_ASSET_IN_USE"
                category = BriefingCategory.ASSETS
                severity = BriefingSeverity.HIGH
                title = f"Asset di riserva usato per Task {assignment.route_id}"
                rationale = (
                    "L'uso di una riserva riduce la capacità di risposta "
                    "a ulteriori indisponibilità."
                )
            else:
                issue_code = "PLANNING_DECISION_WARNING"
                category = BriefingCategory.PLANNING_DECISIONS
                severity = BriefingSeverity.MEDIUM
                title = f"Decisione da verificare per Task {assignment.route_id}"
                rationale = (
                    "Il Planning ha conservato un warning che richiede "
                    "verifica prima della conferma."
                )
            references = [assignment_ref]
            if warning == "DRIVER_ABSENT_REPLACED":
                references.extend(absence_references)
            candidates.append(
                IssueCandidate(
                    issue_code=issue_code,
                    entity_key=f"{assignment_id}:{warning}",
                    title=title,
                    category=category,
                    severity=severity,
                    urgency=3,
                    operational_impact=3,
                    summary=(
                        f"Il Task {assignment.route_id} presenta il warning "
                        f"{warning}."
                    ),
                    rationale=rationale,
                    facts=[
                        _fact(
                            fact_id=f"assignment-{assignment_id}-{warning}",
                            fact_type="assignment_warning",
                            label="Warning Assignment",
                            value=warning,
                            source_type=SourceType.ASSIGNMENT,
                            source_id=assignment_id,
                            source_version=planning_version,
                            observed_at=assignment.updated_at,
                            provenance=FactProvenance.OBSERVED,
                        )
                    ],
                    source_references=references,
                    confidence=assignment.confidence,
                    entity_type="assignment",
                    entity_id=assignment_id,
                )
            )
        if assignment.manual_override:
            reference = _source_reference(
                SourceType.ASSIGNMENT,
                assignment_id,
                planning_version,
                "manual_override",
                "Override manuale",
            )
            candidates.append(
                IssueCandidate(
                    issue_code="MANUAL_OVERRIDE",
                    entity_key=assignment_id,
                    title=f"Override manuale sul Task {assignment.route_id}",
                    category=BriefingCategory.PLANNING_DECISIONS,
                    severity=BriefingSeverity.MEDIUM,
                    urgency=2,
                    operational_impact=3,
                    summary=(
                        "L'Assignment corrente deriva da una modifica "
                        "manuale tracciata."
                    ),
                    rationale=(
                        "Le decisioni manuali devono restare esplicite e "
                        "verificate."
                    ),
                    facts=[
                        _fact(
                            fact_id=f"manual-override-{assignment_id}",
                            fact_type="manual_override",
                            label="Override manuale",
                            value=True,
                            source_type=SourceType.ASSIGNMENT,
                            source_id=assignment_id,
                            source_version=planning_version,
                            observed_at=assignment.updated_at,
                            provenance=FactProvenance.OBSERVED,
                        )
                    ],
                    source_references=[reference],
                    entity_type="assignment",
                    entity_id=assignment_id,
                )
            )
        if assignment.alternatives:
            alternative_assignments.append(assignment)

    if alternative_assignments:
        references = [
            _source_reference(
                SourceType.PLANNING_ALTERNATIVE,
                str(item.id or item.route_id),
                planning_version,
                "alternatives",
                "Alternative non selezionate",
            )
            for item in alternative_assignments[:100]
        ]
        total = sum(len(item.alternatives) for item in alternative_assignments)
        candidates.append(
            IssueCandidate(
                issue_code="PLANNING_ALTERNATIVES_AVAILABLE",
                entity_key=str(bundle.planning.id),
                title="Alternative operative disponibili",
                category=BriefingCategory.PLANNING_DECISIONS,
                severity=BriefingSeverity.INFORMATION,
                urgency=1,
                operational_impact=2,
                summary=(
                    f"Il Planning conserva {total} alternative non scelte "
                    f"per {len(alternative_assignments)} Assignment."
                ),
                rationale=(
                    "Le alternative sono dati consultabili; nessuna viene "
                    "applicata automaticamente."
                ),
                facts=[
                    _fact(
                        fact_id="planning-alternatives-total",
                        fact_type="planning_alternatives",
                        label="Alternative disponibili",
                        value=total,
                        source_type=SourceType.PLANNING_ALTERNATIVE,
                        source_id=str(bundle.planning.id),
                        source_version=planning_version,
                        observed_at=bundle.planning.updated_at,
                        provenance=FactProvenance.OBSERVED,
                    )
                ],
                source_references=references,
                alternatives=[
                    "Aprire il Planning per confrontare le alternative.",
                    "Mantenere l'Assignment corrente senza modifiche.",
                ],
                entity_type="planning",
                entity_id=str(bundle.planning.id),
            )
        )
    return candidates


def _collect_unused_resources(bundle: PlanningBundle) -> list[IssueCandidate]:
    if not bundle.unused_drivers:
        return []
    planning_id = str(bundle.planning.id)
    reference = _source_reference(
        SourceType.PLANNING,
        planning_id,
        str(bundle.planning.version),
        "unused_human_resources",
        "Human Resource non assegnate",
    )
    return [
        IssueCandidate(
            issue_code="HUMAN_RESOURCES_UNUSED",
            entity_key=planning_id,
            title="Human Resource non assegnate",
            category=BriefingCategory.HUMAN_RESOURCES,
            severity=BriefingSeverity.INFORMATION,
            urgency=1,
            operational_impact=1,
            summary=(
                f"{len(bundle.unused_drivers)} Human Resource risultano "
                "disponibili e non assegnate."
            ),
            rationale=(
                "Il dato informa sulle alternative disponibili senza "
                "richiedere una modifica al piano."
            ),
            facts=[
                _fact(
                    fact_id="unused-human-resources",
                    fact_type="unused_human_resources",
                    label="Human Resource non assegnate",
                    value=len(bundle.unused_drivers),
                    source_type=SourceType.PLANNING,
                    source_id=planning_id,
                    source_version=str(bundle.planning.version),
                    observed_at=bundle.planning.updated_at,
                    provenance=FactProvenance.OBSERVED,
                )
            ],
            source_references=[reference],
            alternatives=["Mantenere le risorse libere come disponibilità operativa."],
        )
    ]


def _collect_assets(
    bundle: PlanningBundle,
    assets: list[Asset],
) -> list[IssueCandidate]:
    candidates: list[IssueCandidate] = []
    assigned_plates = {
        item.plate.casefold()
        for item in bundle.assignments
        if item.plate
    }
    operation_day = date.fromisoformat(bundle.planning.operation_date)
    reserve_assets = [
        item for item in assets if item.availability.casefold() == "reserve"
    ]
    for asset in assets:
        asset_id = str(asset.id)
        version = asset.updated_at
        asset_reference = _source_reference(
            SourceType.FLEET_ASSET,
            asset_id,
            version,
            "availability",
            "Disponibilità Asset",
        )
        assigned = bool(
            asset.plate and asset.plate.casefold() in assigned_plates
        )
        availability = asset.availability.casefold()
        status = asset.status.casefold()
        unavailable = availability in {
            "unavailable",
            "maintenance",
        } or status in {"unavailable", "maintenance", "blocked"}
        if unavailable:
            issue_code = (
                "ASSET_UNAVAILABLE_ASSIGNED"
                if assigned
                else "ASSET_UNAVAILABLE"
            )
            candidates.append(
                IssueCandidate(
                    issue_code=issue_code,
                    entity_key=asset.external_identifier,
                    title=(
                        f"Asset {asset.external_identifier} non disponibile"
                    ),
                    category=(
                        BriefingCategory.CRITICAL_ATTENTION
                        if assigned
                        else BriefingCategory.ASSETS
                    ),
                    severity=(
                        BriefingSeverity.CRITICAL
                        if assigned
                        else BriefingSeverity.MEDIUM
                    ),
                    urgency=4 if assigned else 2,
                    operational_impact=4 if assigned else 2,
                    summary=(
                        f"Stato osservato: {asset.status}; disponibilità: "
                        f"{asset.availability}."
                    ),
                    rationale=(
                        "L'Asset risulta assegnato nonostante l'indisponibilità."
                        if assigned
                        else "L'indisponibilità riduce il parco utilizzabile."
                    ),
                    facts=[
                        _fact(
                            fact_id=f"asset-{asset_id}-availability",
                            fact_type="resource_availability",
                            label="Disponibilità Asset",
                            value=asset.availability,
                            source_type=SourceType.FLEET_ASSET,
                            source_id=asset_id,
                            source_version=version,
                            observed_at=asset.updated_at,
                            provenance=FactProvenance.OBSERVED,
                        )
                    ],
                    source_references=[asset_reference],
                    entity_type="asset",
                    entity_id=asset_id,
                )
            )
        if (
            asset in reserve_assets
            and assigned
            and len(reserve_assets) == 1
        ):
            candidates.append(
                IssueCandidate(
                    issue_code="RESERVE_ASSET_IN_USE",
                    entity_key=asset.external_identifier,
                    title="Ultimo Asset di riserva in uso",
                    category=BriefingCategory.ASSETS,
                    severity=BriefingSeverity.HIGH,
                    urgency=3,
                    operational_impact=3,
                    summary=(
                        f"L'Asset {asset.external_identifier}, unica riserva "
                        "osservata nel Fleet Plugin, risulta assegnato."
                    ),
                    rationale=(
                        "Non rimangono Asset esplicitamente classificati "
                        "come riserva."
                    ),
                    facts=[
                        _fact(
                            fact_id=f"asset-{asset_id}-reserve-use",
                            fact_type="reserve_asset_use",
                            label="Asset di riserva assegnato",
                            value=True,
                            source_type=SourceType.FLEET_ASSET,
                            source_id=asset_id,
                            source_version=version,
                            observed_at=asset.updated_at,
                            provenance=FactProvenance.DERIVED,
                        )
                    ],
                    source_references=[asset_reference],
                    entity_type="asset",
                    entity_id=asset_id,
                )
            )
        for document in asset.documents:
            if not document.expires_on:
                continue
            try:
                expiration = date.fromisoformat(document.expires_on)
            except ValueError:
                continue
            if expiration > operation_day + timedelta(days=30):
                continue
            expired = expiration < operation_day
            issue_code = (
                "ASSET_DOCUMENT_EXPIRED"
                if expired
                else "ASSET_DOCUMENT_EXPIRING"
            )
            document_id = str(document.id)
            document_reference = _source_reference(
                SourceType.FLEET_DOCUMENT,
                document_id,
                document.created_at,
                "expires_on",
                "Scadenza documento Asset",
            )
            candidates.append(
                IssueCandidate(
                    issue_code=issue_code,
                    entity_key=document_id,
                    title=(
                        f"Documento scaduto per {asset.external_identifier}"
                        if expired
                        else f"Documento in scadenza per {asset.external_identifier}"
                    ),
                    category=BriefingCategory.ASSETS,
                    severity=(
                        BriefingSeverity.HIGH
                        if expired
                        else BriefingSeverity.MEDIUM
                    ),
                    urgency=3 if expired else 2,
                    operational_impact=3,
                    summary=(
                        f"{document.name} ha scadenza "
                        f"{document.expires_on}."
                    ),
                    rationale=(
                        "La validità documentale può influire sulla "
                        "disponibilità operativa dell'Asset."
                    ),
                    facts=[
                        _fact(
                            fact_id=f"document-{document_id}-expiration",
                            fact_type="asset_document_expiration",
                            label="Scadenza documento",
                            value=document.expires_on,
                            source_type=SourceType.FLEET_DOCUMENT,
                            source_id=document_id,
                            source_version=document.created_at,
                            observed_at=document.created_at,
                            provenance=FactProvenance.OBSERVED,
                        )
                    ],
                    source_references=[asset_reference, document_reference],
                    entity_type="asset",
                    entity_id=asset_id,
                )
            )
    return candidates


def _collect_dashboard_issues(
    dashboard: OperationsDashboard | None,
    snapshot_id: int | None,
) -> list[IssueCandidate]:
    if not dashboard:
        return []
    candidates: list[IssueCandidate] = []
    ignored = {
        "LOW_RESERVE_MARGIN",
        "INSUFFICIENT_OPERATIONAL_VEHICLES",
    }
    grouped: dict[tuple[str, str, str, str, str], list[tuple[int, object]]] = {}
    for index, issue in enumerate(dashboard.issues):
        if issue.code not in ignored:
            key = (
                issue.code,
                issue.severity.value,
                issue.entity_ref,
                issue.description,
                issue.reason,
            )
            grouped.setdefault(key, []).append((index, issue))

    for group in grouped.values():
        index, issue = group[0]
        category = BriefingCategory.PLANNING_DECISIONS
        mapped_code = "PLANNING_DECISION_WARNING"
        if "DRIVER" in issue.code:
            category = BriefingCategory.HUMAN_RESOURCES
        if "VEHICLE" in issue.code:
            category = BriefingCategory.ASSETS
        if issue.code == "UNAVAILABLE_VEHICLE_ASSIGNED":
            mapped_code = "ASSET_UNAVAILABLE_ASSIGNED"
        if issue.code == "UNKNOWN_STATION":
            mapped_code = "OPERATIONAL_UNIT_UNRECOGNIZED"
        severity = _severity_from_source(issue.severity.value)
        if severity == BriefingSeverity.CRITICAL:
            category = BriefingCategory.CRITICAL_ATTENTION
        source_id = f"operation-snapshot:{snapshot_id}:issue:{index}"
        references = [
            _source_reference(
                SourceType.CONFLICT,
                f"operation-snapshot:{snapshot_id}:issue:{item_index}",
                dashboard.generated_at,
                "issues",
                "Conflitto operativo",
            )
            for item_index, _ in group[:100]
        ]
        occurrence_count = len(group)
        title = issue.description
        summary = issue.reason
        if issue.code == "UNKNOWN_STATION":
            title = "Operational Unit non riconosciuta"
            summary = (
                f"{occurrence_count} righe dell'analisi indicano la stessa "
                "Operational Unit non riconosciuta."
            )
        elif occurrence_count > 1:
            summary = (
                f"{occurrence_count} occorrenze. {issue.reason}"
            )
        candidates.append(
            IssueCandidate(
                issue_code=mapped_code,
                entity_key=f"{issue.code}:{issue.entity_ref}",
                title=title,
                category=category,
                severity=severity,
                urgency=4 if severity == BriefingSeverity.CRITICAL else 2,
                operational_impact=(
                    4 if severity == BriefingSeverity.CRITICAL else 2
                ),
                summary=summary,
                rationale=(
                    "Il conflitto proviene dall'ultima analisi operativa "
                    "persistita."
                ),
                facts=[
                    _fact(
                        fact_id=f"conflict-{snapshot_id}-{index}",
                        fact_type="operational_conflict",
                        label="Conflitto operativo",
                        value=issue.code,
                        source_type=SourceType.CONFLICT,
                        source_id=source_id,
                        source_version=dashboard.generated_at,
                        observed_at=dashboard.generated_at,
                        provenance=FactProvenance.OBSERVED,
                    )
                ],
                source_references=references,
                entity_type="operational_entity",
                entity_id=issue.entity_ref,
                fallback_recommendation=issue.suggested_action,
            )
        )
    return candidates


def collect_issue_candidates(
    *,
    bundle: PlanningBundle,
    dashboard: OperationsDashboard | None,
    dashboard_snapshot_id: int | None,
    assets: list[Asset],
) -> list[IssueCandidate]:
    return [
        *_collect_uncovered_tasks(bundle),
        *_collect_capacity(bundle),
        *_readiness_candidate(dashboard, dashboard_snapshot_id),
        *_collect_assignments(bundle),
        *_collect_unused_resources(bundle),
        *_collect_assets(bundle, assets),
        *_collect_dashboard_issues(dashboard, dashboard_snapshot_id),
    ]


def build_ranked_sections(
    candidates: list[IssueCandidate],
) -> list[BriefingSection]:
    ranked = sorted(
        candidates,
        key=lambda candidate: (
            -priority_score(
                candidate.severity,
                candidate.urgency,
                candidate.operational_impact,
            ),
            candidate.issue_code,
            candidate.entity_key,
        ),
    )
    sections: list[BriefingSection] = []
    for rank, candidate in enumerate(ranked[:300], start=1):
        references = _deduplicate_references(
            candidate.source_references
        )
        recommendation = recommendation_for(
            issue_code=candidate.issue_code,
            reason=candidate.rationale,
            source_references=references,
            entity_type=candidate.entity_type,
            entity_id=candidate.entity_id,
            fallback_text=candidate.fallback_recommendation,
        )
        action_links: list[ActionLink] = []
        if recommendation and recommendation.action_link:
            action_links.append(recommendation.action_link)
        elif candidate.issue_code == "PLANNING_ALTERNATIVES_AVAILABLE":
            action_links.append(
                ActionLink(
                    label="Apri Planning",
                    workspace=WorkspaceTarget.OPERATIONS,
                    target_id="planningSection",
                    entity_type=candidate.entity_type,
                    entity_id=candidate.entity_id,
                )
            )
        sections.append(
            BriefingSection(
                section_id=_stable_section_id(
                    candidate.issue_code,
                    candidate.entity_key,
                ),
                issue_code=candidate.issue_code,
                title=candidate.title,
                category=candidate.category,
                severity=candidate.severity,
                priority=rank,
                priority_score=priority_score(
                    candidate.severity,
                    candidate.urgency,
                    candidate.operational_impact,
                ),
                urgency=candidate.urgency,
                operational_impact=candidate.operational_impact,
                ranking_explanation=ranking_explanation(
                    candidate.severity,
                    candidate.urgency,
                    candidate.operational_impact,
                ),
                summary=candidate.summary,
                facts=candidate.facts,
                recommendation=recommendation,
                rationale=candidate.rationale,
                alternatives=candidate.alternatives,
                source_references=references,
                action_links=action_links,
                confidence=candidate.confidence,
                requires_human_decision=recommendation is not None,
            )
        )
    return sections
