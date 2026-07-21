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
from app.plugins.fleet.domain.sync_models import FleetBriefingSnapshot
from app.plugins.workforce.domain.models import WorkforceBriefingSnapshot


def _workforce_section(snapshot: WorkforceBriefingSnapshot) -> BriefingSection | None:
    coverage = snapshot.coverage
    requires_attention = bool(
        coverage.status == "deficit"
        or snapshot.absences
        or snapshot.contracts_expiring
        or snapshot.missing_capabilities
    )
    if not requires_attention:
        return None
    severity = (
        BriefingSeverity.HIGH
        if coverage.status == "deficit" or snapshot.missing_capabilities
        else BriefingSeverity.MEDIUM
    )
    source = SourceReference(
        source_type=SourceType.WORKFORCE,
        source_id=f"workforce:{snapshot.date}",
        source_version=snapshot.date,
        field_path="briefing_snapshot",
        label="Disponibilita Workforce",
    )
    facts = [
        BriefingFact(
            fact_id=f"workforce-coverage-{snapshot.date}",
            fact_type="workforce_coverage",
            label="Copertura Workforce",
            value={
                "required": coverage.required,
                "available": coverage.available,
                "margin": coverage.margin,
                "status": coverage.status,
            },
            source_type=SourceType.WORKFORCE,
            source_id=source.source_id,
            source_version=snapshot.date,
            provenance=FactProvenance.DERIVED,
        )
    ]
    return BriefingSection(
        section_id=f"workforce-{snapshot.date}",
        issue_code=("WORKFORCE_DEFICIT" if coverage.status == "deficit" else "WORKFORCE_ATTENTION"),
        title="Copertura Workforce",
        category=BriefingCategory.HUMAN_RESOURCES,
        severity=severity,
        priority=1,
        priority_score=82 if severity is BriefingSeverity.HIGH else 58,
        urgency=3,
        operational_impact=4 if severity is BriefingSeverity.HIGH else 2,
        ranking_explanation="Priorita determinata dal contratto pubblico Workforce.",
        summary=(
            f"Disponibili {coverage.available}; assenze {snapshot.absences}; "
            f"margine {coverage.margin if coverage.margin is not None else 'non disponibile'}."
        ),
        facts=facts,
        rationale="Il briefing espone il riepilogo calcolato dal Workforce Plugin senza ricalcolarlo.",
        alternatives=["Verificare il calendario Workforce e il fabbisogno configurato."],
        source_references=[source],
        action_links=[
            ActionLink(
                label="Apri Workforce",
                workspace=WorkspaceTarget.WORKFORCE,
                target_id="workforceSection",
            )
        ],
        confidence=1.0,
    )


def _fleet_section(snapshot: FleetBriefingSnapshot) -> BriefingSection | None:
    attention = (
        snapshot.unavailable_assets
        + snapshot.maintenance_assets
        + snapshot.documents_attention
        + snapshot.unresolved_conflicts
    )
    if not attention:
        return None
    severity = (
        BriefingSeverity.HIGH
        if snapshot.unresolved_conflicts or snapshot.maintenance_assets
        else BriefingSeverity.MEDIUM
    )
    source = SourceReference(
        source_type=SourceType.FLEET_SYNC,
        source_id="fleet:registry",
        field_path="briefing_snapshot",
        label="Stato Asset Registry",
    )
    return BriefingSection(
        section_id="fleet-registry-attention",
        issue_code="FLEET_REGISTRY_ATTENTION",
        title="Stato Asset Registry",
        category=BriefingCategory.ASSETS,
        severity=severity,
        priority=1,
        priority_score=78 if severity is BriefingSeverity.HIGH else 54,
        urgency=3,
        operational_impact=3,
        ranking_explanation="Priorita determinata dal contratto pubblico Fleet.",
        summary=(
            f"Officina {snapshot.maintenance_assets}; indisponibili "
            f"{snapshot.unavailable_assets}; conflitti {snapshot.unresolved_conflicts}; "
            f"documenti in attenzione {snapshot.documents_attention}."
        ),
        facts=[
            BriefingFact(
                fact_id="fleet-registry-summary",
                fact_type="fleet_registry_summary",
                label="Riepilogo Fleet",
                value=snapshot.model_dump(mode="json"),
                source_type=SourceType.FLEET_SYNC,
                source_id=source.source_id,
                provenance=FactProvenance.DERIVED,
            )
        ],
        rationale="Il briefing consuma i conteggi pubblicati dal Fleet Plugin.",
        alternatives=["Aprire Fleet e risolvere le proposte non confermate."],
        source_references=[source],
        action_links=[
            ActionLink(
                label="Apri Fleet",
                workspace=WorkspaceTarget.FLEET,
                target_id="fleetPluginSection",
            )
        ],
        confidence=1.0,
    )


def merge_plugin_sections(
    sections: list[BriefingSection],
    workforce: WorkforceBriefingSnapshot | None,
    fleet: FleetBriefingSnapshot | None,
) -> list[BriefingSection]:
    additions = [
        item for item in (
            _workforce_section(workforce) if workforce else None,
            _fleet_section(fleet) if fleet else None,
        ) if item
    ]
    ranked = sorted(
        [*sections, *additions],
        key=lambda item: (-item.priority_score, item.issue_code, item.section_id),
    )
    return [item.model_copy(update={"priority": index}) for index, item in enumerate(ranked, start=1)]
