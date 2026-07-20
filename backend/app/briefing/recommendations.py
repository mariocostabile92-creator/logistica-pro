from dataclasses import dataclass

from app.briefing.models import (
    ActionLink,
    BriefingRecommendation,
    SourceReference,
    WorkspaceTarget,
)


@dataclass(frozen=True)
class RecommendationRule:
    text: str
    expected_impact: str
    workspace: WorkspaceTarget
    target_id: str
    alternatives: tuple[str, ...] = ()


RULES = {
    "TASK_UNCOVERED": RecommendationRule(
        text="Rivedi il Task scoperto e valuta una delle risorse alternative disponibili.",
        expected_impact="Ripristinare la copertura del piano prima dell'avvio.",
        workspace=WorkspaceTarget.OPERATIONS,
        target_id="planningSection",
        alternatives=(
            "Ridurre consapevolmente il perimetro operativo.",
            "Confermare una risorsa aggiuntiva.",
        ),
    ),
    "CAPACITY_SHORTAGE": RecommendationRule(
        text="Verifica la capacità dell'Operational Unit prima di confermare il piano.",
        expected_impact="Eliminare il deficit tra domanda e capacità disponibile.",
        workspace=WorkspaceTarget.OPERATIONS,
        target_id="dashboardSection",
    ),
    "RESERVE_MARGIN_LOW": RecommendationRule(
        text="Mantieni un Asset libero come riserva o approva consapevolmente il margine ridotto.",
        expected_impact="Aumentare la resilienza in caso di indisponibilità durante la giornata.",
        workspace=WorkspaceTarget.OPERATIONS,
        target_id="dashboardSection",
    ),
    "HUMAN_RESOURCE_SUBSTITUTED": RecommendationRule(
        text="Conferma la sostituzione della Human Resource assente.",
        expected_impact="Rendere esplicita e verificata la copertura del Task coinvolto.",
        workspace=WorkspaceTarget.OPERATIONS,
        target_id="planningSection",
    ),
    "ASSET_UNAVAILABLE_ASSIGNED": RecommendationRule(
        text="Verifica immediatamente l'Asset assegnato e scegli un'alternativa prima dell'avvio.",
        expected_impact="Evitare un Assignment basato su un Asset non disponibile.",
        workspace=WorkspaceTarget.FLEET,
        target_id="fleetPluginSection",
    ),
    "ASSET_UNAVAILABLE": RecommendationRule(
        text="Verifica lo stato osservato dell'Asset nel Fleet Plugin.",
        expected_impact="Confermare che l'Asset resti escluso dalle operazioni finché non disponibile.",
        workspace=WorkspaceTarget.FLEET,
        target_id="fleetPluginSection",
    ),
    "RESERVE_ASSET_IN_USE": RecommendationRule(
        text="Valuta se liberare l'ultimo Asset classificato come riserva.",
        expected_impact="Ripristinare una capacità di risposta agli imprevisti.",
        workspace=WorkspaceTarget.FLEET,
        target_id="fleetPluginSection",
    ),
    "MANUAL_OVERRIDE": RecommendationRule(
        text="Rivedi l'override manuale e conferma che la motivazione sia ancora valida.",
        expected_impact="Mantenere tracciabile la decisione operativa.",
        workspace=WorkspaceTarget.OPERATIONS,
        target_id="planningSection",
    ),
    "PLANNING_DECISION_WARNING": RecommendationRule(
        text="Verifica il warning associato all'Assignment prima della conferma.",
        expected_impact="Confermare che il rischio residuo sia stato compreso.",
        workspace=WorkspaceTarget.OPERATIONS,
        target_id="planningSection",
    ),
    "READINESS_ATTENTION": RecommendationRule(
        text="Rivedi le motivazioni della Readiness e conferma le condizioni operative.",
        expected_impact="Rendere esplicita l'accettazione dei warning prima dell'avvio.",
        workspace=WorkspaceTarget.OPERATIONS,
        target_id="dashboardSection",
    ),
    "READINESS_CRITICAL": RecommendationRule(
        text="Risolvi le condizioni bloccanti indicate dalla Readiness prima dell'avvio.",
        expected_impact="Portare il sistema in una condizione operativa verificabile.",
        workspace=WorkspaceTarget.OPERATIONS,
        target_id="dashboardSection",
    ),
    "ASSET_DOCUMENT_EXPIRED": RecommendationRule(
        text="Verifica il documento scaduto prima di utilizzare l'Asset.",
        expected_impact="Evitare l'impiego di un Asset con documentazione non valida.",
        workspace=WorkspaceTarget.FLEET,
        target_id="fleetPluginSection",
    ),
    "ASSET_DOCUMENT_EXPIRING": RecommendationRule(
        text="Pianifica la verifica del documento prossimo alla scadenza.",
        expected_impact="Ridurre il rischio di indisponibilità futura dell'Asset.",
        workspace=WorkspaceTarget.FLEET,
        target_id="fleetPluginSection",
    ),
    "OPERATIONAL_UNIT_UNRECOGNIZED": RecommendationRule(
        text="Verifica l'Operational Unit o aggiorna il mapping configurato.",
        expected_impact=(
            "Rendere esplicito il perimetro operativo usato dall'analisi."
        ),
        workspace=WorkspaceTarget.SETTINGS,
        target_id="settingsSection",
    ),
}


def recommendation_for(
    *,
    issue_code: str,
    reason: str,
    source_references: list[SourceReference],
    entity_type: str | None = None,
    entity_id: str | None = None,
    fallback_text: str | None = None,
) -> BriefingRecommendation | None:
    rule = RULES.get(issue_code)
    if not rule and not fallback_text:
        return None
    text = rule.text if rule else fallback_text
    expected_impact = (
        rule.expected_impact
        if rule
        else "Ridurre il rischio operativo attraverso una verifica umana."
    )
    action_link = None
    alternatives: list[str] = []
    if rule:
        action_link = ActionLink(
            label="Apri dettaglio",
            workspace=rule.workspace,
            target_id=rule.target_id,
            entity_type=entity_type,
            entity_id=entity_id,
        )
        alternatives = list(rule.alternatives)
    return BriefingRecommendation(
        recommendation_code=f"RECOMMEND_{issue_code}",
        text=text,
        reason=reason,
        data_used=source_references,
        alternatives=alternatives,
        expected_impact=expected_impact,
        requires_human_confirmation=True,
        action_link=action_link,
    )
