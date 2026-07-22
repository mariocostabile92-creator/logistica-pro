from app.domain.planning_publication.models import (
    PlanningPublicationPolicy,
    PlanningPublicationResult,
    PlanningPublicationRuleResult,
    PlanningPublicationState,
    PlanningPublicationValidationContext,
)


class PlanningPublicationValidator:
    def __init__(self, policy: PlanningPublicationPolicy) -> None:
        self._policy = policy

    @staticmethod
    def _rule(
        code: str,
        passed: bool,
        success: str,
        failure: str,
        remediation_hint: str,
    ) -> PlanningPublicationRuleResult:
        return PlanningPublicationRuleResult(
            code=code,
            passed=passed,
            reason=success if passed else failure,
            remediation_hint=remediation_hint,
        )

    def validate(
        self,
        context: PlanningPublicationValidationContext,
    ) -> PlanningPublicationResult:
        confirmation = context.confirmation
        confirmation_present = confirmation is not None
        confirmation_valid = (
            not self._policy.require_valid_confirmation
            or bool(
                confirmation_present
                and confirmation.state
                is self._policy.required_confirmation_state
                and confirmation.validation.can_confirm
                and confirmation.validation.state.value == "READY_TO_CONFIRM"
                and all(rule.passed for rule in confirmation.validation.rules)
            )
        )
        no_active = (
            not self._policy.require_unique_active_publication
            or context.active_publication is None
        )
        runtime_compatible = (
            not self._policy.require_runtime_compatibility
            or context.runtime_compatible
        )
        fingerprint_coherent = (
            not self._policy.require_fingerprint_match
            or bool(
                confirmation_present
                and context.requested_confirmation_fingerprint
                == confirmation.fingerprint
            )
        )
        version_coherent = (
            not self._policy.require_version_match
            or bool(
                confirmation_present
                and context.requested_confirmation_id
                == confirmation.confirmation_id
                and context.requested_confirmation_version
                == confirmation.version
            )
        )
        operational_unit_valid = (
            not self._policy.require_valid_operational_unit
            or bool(
                confirmation_present
                and context.operational_unit_valid
                and confirmation.scope.organization_id
                == context.scope.organization_id
                and confirmation.scope.operational_unit.external_identifier
                == context.scope.operational_unit.external_identifier
                and confirmation.scope.planning_date
                == context.scope.planning_date
            )
        )

        rules = (
            self._rule(
                "CONFIRMED_PLAN_PRESENT",
                confirmation_present,
                "Confirmed Plan disponibile.",
                "Nessun Confirmed Plan disponibile per il contesto richiesto.",
                "Conferma il Draft nel Planning Workspace.",
            ),
            self._rule(
                "CONFIRMATION_VALID",
                confirmation_valid,
                "Conferma valida e immutabile.",
                "La conferma non supera il contratto di validita richiesto.",
                "Ripeti la validazione e la conferma del Draft.",
            ),
            self._rule(
                "NO_ACTIVE_PUBLICATION",
                no_active,
                "Nessuna Publication attiva per il contesto.",
                "Esiste gia un Published Plan per il contesto.",
                "Consulta la Publication corrente e la relativa cronologia.",
            ),
            self._rule(
                "RUNTIME_COMPATIBLE",
                runtime_compatible,
                "Runtime compatibile secondo la Confirmation congelata.",
                "La Confirmation non attesta un Runtime compatibile.",
                "Risolvi la compatibilita Runtime e crea una nuova conferma valida.",
            ),
            self._rule(
                "FINGERPRINT_COHERENT",
                fingerprint_coherent,
                "Fingerprint del Confirmed Plan coerente.",
                "Il fingerprint richiesto non coincide con il Confirmed Plan.",
                "Ricarica il Confirmed Plan corrente e ripeti la validazione.",
            ),
            self._rule(
                "VERSION_COHERENT",
                version_coherent,
                "Versione del Confirmed Plan coerente.",
                "Identita o versione della conferma non coincidono.",
                "Ricarica la Confirmation corrente prima di pubblicare.",
            ),
            self._rule(
                "OPERATIONAL_UNIT_VALID",
                operational_unit_valid,
                "Operational Unit coerente con il Confirmed Plan.",
                "Operational Unit, organizzazione o data non sono coerenti.",
                "Seleziona il contesto operativo associato alla conferma.",
            ),
        )
        can_publish = all(rule.passed for rule in rules)
        state = (
            PlanningPublicationState.READY_TO_PUBLISH
            if can_publish
            else PlanningPublicationState.NOT_PUBLISHED
        )
        failed = tuple(rule for rule in rules if not rule.passed)
        rationale = (
            "Tutte le regole sono superate. Il Confirmed Plan puo essere pubblicato."
            if can_publish
            else f"Publication non disponibile: {failed[0].reason}"
        )
        return PlanningPublicationResult(
            state=state,
            can_publish=can_publish,
            rules=rules,
            rationale=rationale,
            evaluated_at=context.evaluated_at,
        )
