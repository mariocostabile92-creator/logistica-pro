from app.domain.planning_confirmation.models import (
    PlanningConfirmationPolicy,
    PlanningConfirmationResult,
    PlanningConfirmationRuleResult,
    PlanningConfirmationState,
    PlanningConfirmationValidationContext,
)
from app.domain.planning_drafts import PlanningDraftState
from app.domain.planning_inputs import PlanningInputStatus


class PlanningConfirmationValidator:
    def __init__(self, policy: PlanningConfirmationPolicy) -> None:
        self._policy = policy

    @staticmethod
    def _rule(
        code: str,
        passed: bool,
        success: str,
        failure: str,
        remediation_hint: str,
    ) -> PlanningConfirmationRuleResult:
        return PlanningConfirmationRuleResult(
            code=code,
            passed=passed,
            reason=success if passed else failure,
            remediation_hint=remediation_hint,
        )

    def validate(
        self,
        context: PlanningConfirmationValidationContext,
    ) -> PlanningConfirmationResult:
        draft = context.draft
        draft_present = draft is not None
        draft_saved = (
            not self._policy.require_saved_draft
            or bool(draft_present and draft.state is PlanningDraftState.SAVED)
        )
        readiness_ready = (
            context.readiness.status
            is self._policy.required_readiness_status
        )
        blocking_conflicts = tuple(
            item
            for item in context.conflicts.report.conflicts
            if item.blocking
        )
        no_blockers = (
            not self._policy.require_no_blocking_conflicts
            or (
                not context.readiness.blockers
                and not blocking_conflicts
            )
        )
        runtime_compatible = (
            context.runtime_compatible
            and context.runtime_status.casefold()
            == self._policy.required_runtime_status.casefold()
        )
        envelope = context.envelope
        envelope_valid = (
            not self._policy.require_valid_envelope
            or bool(
                envelope is not None
                and all(
                    item.status is PlanningInputStatus.READY
                    for item in envelope.validation
                )
                and envelope.version.value
                == context.readiness.envelope_version
                and envelope.fingerprint
                == context.readiness.envelope_fingerprint
            )
        )
        version_coherent = bool(
            draft_present
            and context.requested_draft_id == draft.draft_id
            and context.requested_draft_version == draft.version.number
        )
        no_active = (
            not self._policy.require_unique_active_confirmation
            or context.active_confirmation is None
        )

        rules = (
            self._rule(
                "DRAFT_PRESENT",
                draft_present,
                "Draft disponibile.",
                "Nessun Draft disponibile per il contesto richiesto.",
                "Crea un Draft nel Planning Workspace.",
            ),
            self._rule(
                "DRAFT_SAVED",
                draft_saved,
                "Il Draft e salvato.",
                "Il Draft non e nello stato SAVED.",
                "Salva il Draft prima della conferma.",
            ),
            self._rule(
                "READINESS_READY",
                readiness_ready,
                "Planning Readiness in stato READY.",
                "Planning Readiness non e nello stato READY.",
                "Risolvi i problemi Readiness e ripeti la verifica.",
            ),
            self._rule(
                "NO_CRITICAL_BLOCKERS",
                no_blockers,
                "Nessun blocker critico presente.",
                "Sono presenti blocker che impediscono la conferma.",
                "Apri Conflict Review e risolvi tutti i blocker.",
            ),
            self._rule(
                "RUNTIME_COMPATIBLE",
                runtime_compatible,
                "Planning Runtime compatibile.",
                "Planning Runtime non compatibile con la conferma.",
                "Allinea scope, sorgenti e versioni degli input.",
            ),
            self._rule(
                "ENVELOPE_VALID",
                envelope_valid,
                "PlanningInputEnvelope valido e coerente.",
                "PlanningInputEnvelope assente, invalido o non coerente.",
                "Rigenera gli input Planning da Workforce e Fleet.",
            ),
            self._rule(
                "DRAFT_VERSION_COHERENT",
                version_coherent,
                "Versione Draft coerente con la richiesta.",
                "Il Draft e stato modificato o la versione non coincide.",
                "Ricarica il Draft corrente e ripeti la validazione.",
            ),
            self._rule(
                "NO_ACTIVE_CONFIRMATION",
                no_active,
                "Nessuna conferma attiva per il contesto.",
                "Esiste gia un Confirmed Plan per il contesto.",
                "Consulta la conferma esistente. La pubblicazione sara gestita in PW-8.",
            ),
        )
        can_confirm = all(rule.passed for rule in rules)
        state = (
            PlanningConfirmationState.READY_TO_CONFIRM
            if can_confirm
            else PlanningConfirmationState.NOT_READY
        )
        failed = tuple(rule for rule in rules if not rule.passed)
        rationale = (
            "Tutte le regole sono superate. Il Draft puo essere confermato."
            if can_confirm
            else f"Conferma non disponibile: {failed[0].reason}"
        )
        return PlanningConfirmationResult(
            state=state,
            can_confirm=can_confirm,
            rules=rules,
            rationale=rationale,
            evaluated_at=context.evaluated_at,
        )
