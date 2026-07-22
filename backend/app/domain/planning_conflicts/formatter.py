import hashlib

from app.domain.planning_conflicts.catalog import (
    PLANNING_CONFLICT_TEMPLATES,
    PlanningConflictTemplate,
)
from app.domain.planning_conflicts.models import (
    PlanningConflict,
    PlanningConflictCategory,
    PlanningConflictDiagnostic,
    PlanningConflictSeverity,
    PlanningConflictSuggestion,
)
from app.domain.planning_readiness import PlanningReadinessResult


_FALLBACK = PlanningConflictTemplate(
    category=PlanningConflictCategory.VALIDATION,
    severity=PlanningConflictSeverity.MEDIUM,
    title="Dato operativo da verificare",
    description="Un controllo Core richiede una verifica esplicita.",
    action="Correggi il dato indicato nel workspace sorgente e aggiorna lo snapshot.",
    workspace="Source Workspace",
    rationale="Il conflitto proviene da un contratto Core validato.",
    documentation_reference=(
        "PLANNING_WORKSPACE_CONTRACT_INVENTORY.md#planning-readiness"
    ),
)


class PlanningConflictFormatter:
    def format(
        self,
        *,
        code: str,
        source: str,
        blocking: bool,
        diagnostic: PlanningConflictDiagnostic,
        readiness: PlanningReadinessResult,
        affected_entities: tuple[str, ...] = (),
    ) -> PlanningConflict:
        known_template = code in PLANNING_CONFLICT_TEMPLATES
        template = PLANNING_CONFLICT_TEMPLATES.get(code, _FALLBACK)
        stable_identity = "|".join(
            (
                code,
                source,
                readiness.operational_unit.external_identifier,
                readiness.planning_date.isoformat(),
                *affected_entities,
            )
        )
        conflict_id = "conflict-" + hashlib.sha256(
            stable_identity.encode("utf-8")
        ).hexdigest()[:16]
        description = template.description
        if diagnostic.message and diagnostic.message != description:
            description = f"{description} Dettaglio: {diagnostic.message}"
        severity = template.severity
        if blocking and severity in {
            PlanningConflictSeverity.INFO,
            PlanningConflictSeverity.LOW,
            PlanningConflictSeverity.MEDIUM,
        }:
            severity = PlanningConflictSeverity.HIGH
        title = template.title if known_template else diagnostic.message.rstrip(".")
        suggestion_action = template.action
        suggestion_workspace = template.workspace
        suggestion_rationale = template.rationale
        if not known_template:
            if diagnostic.details:
                suggestion_rationale = diagnostic.details[0]
                suggestion_action = diagnostic.details[-1]
            if source in {"workforce", "fleet"}:
                suggestion_workspace = source.title()
        return PlanningConflict(
            id=conflict_id,
            code=code,
            category=template.category,
            severity=severity,
            title=title,
            description=description,
            operational_unit=readiness.operational_unit,
            planning_date=readiness.planning_date,
            source=source,
            blocking=blocking,
            affected_entities=affected_entities,
            diagnostics=(diagnostic,),
            suggestion=PlanningConflictSuggestion(
                action=suggestion_action,
                workspace=suggestion_workspace,
                rationale=suggestion_rationale,
            ),
            documentation_reference=template.documentation_reference,
            timestamp=readiness.evaluated_at,
        )
