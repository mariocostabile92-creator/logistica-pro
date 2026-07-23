from app.domain.execution_attempt import ExecutionAttemptStatus
from app.domain.execution_intent import (
    ExecutionIntentMode,
    ExecutionIntentStatus,
    ExecutionPublicationStatus,
)
from app.domain.planning_runtime import PlanningRuntimeOutputStatus
from app.domain.runtime_authority import (
    AuthorityDecisionMode,
    AuthorityResolutionState,
)
from app.domain.runtime_canary import (
    RuntimeCanaryDecision,
    RuntimeCanaryStatus,
)
from app.domain.runtime_primary.models import (
    RuntimeCertificationDecision,
    RuntimeCertificationGateStatus,
    RuntimePrimaryEvaluationContext,
    RuntimePrimaryMode,
    RuntimePrimaryPolicy,
    RuntimePrimaryValidationResult,
    RuntimePrimaryValidationRule,
)
from app.domain.runtime_shadow import RuntimeShadowState


class RuntimePrimaryValidator:
    def __init__(self, policy: RuntimePrimaryPolicy) -> None:
        self._policy = policy

    @staticmethod
    def _rule(
        code: str,
        passed: bool,
        success: str,
        failure: str,
        remediation: str,
    ) -> RuntimePrimaryValidationRule:
        return RuntimePrimaryValidationRule(
            code=code,
            passed=passed,
            reason=success if passed else failure,
            remediation_hint=remediation,
        )

    def validate(
        self,
        context: RuntimePrimaryEvaluationContext,
    ) -> RuntimePrimaryValidationResult:
        if context.requested_mode is RuntimePrimaryMode.DISABLED:
            rules = (
                self._rule(
                    "PROMOTION_MODE_DISABLED",
                    False,
                    "Runtime Primary abilitato.",
                    "Runtime Primary disabilitato.",
                    "Mantenere il Legacy come unico writer.",
                ),
            )
        elif context.requested_mode is RuntimePrimaryMode.ROLLBACK:
            rules = self._rollback_rules(context)
        elif context.requested_mode is RuntimePrimaryMode.CANARY:
            rules = self._canary_rules(context)
        else:
            rules = self._primary_rules(context)
        return RuntimePrimaryValidationResult(
            allowed=all(rule.passed for rule in rules),
            rules=rules,
            evaluated_at=context.evaluated_at,
        )

    def _primary_rules(
        self,
        context: RuntimePrimaryEvaluationContext,
    ) -> tuple[RuntimePrimaryValidationRule, ...]:
        authority = context.authority
        decision = authority.decision
        canary = context.canary
        canary_metrics = canary.report.metrics if canary else None
        comparator = context.comparator
        runtime_output = context.runtime_output
        certification = context.certification
        gate_by_code = {gate.code: gate for gate in certification.gates}

        authority_valid = bool(
            authority.state is AuthorityResolutionState.WRITE_ALLOWED
            and decision is not None
            and decision.mode is AuthorityDecisionMode.RUNTIME
        )
        publication_valid = (
            context.publication.status is ExecutionPublicationStatus.PUBLISHED
        )
        intent_valid = (
            context.intent.status is ExecutionIntentStatus.READY
            and context.intent.scope.execution_mode
            is ExecutionIntentMode.NORMAL
        )
        attempt_valid = bool(
            context.attempt is not None
            and context.attempt.status
            is ExecutionAttemptStatus.READY_TO_EXECUTE
        )
        canary_valid = bool(
            canary is not None
            and canary.session.status is RuntimeCanaryStatus.FINISHED
            and canary.report.decision is RuntimeCanaryDecision.PASS
        )
        parity_valid = bool(
            canary_metrics is not None
            and canary_metrics.parity_percent
            >= self._policy.minimum_parity_percent
        )
        critical_valid = bool(
            canary_metrics is not None
            and canary_metrics.critical_mismatch
            <= self._policy.maximum_critical_mismatch
        )
        duplicate_valid = bool(
            canary_metrics is not None
            and canary_metrics.duplicate_execution
            <= self._policy.maximum_duplicate_execution
        )
        comparator_valid = bool(
            comparator is not None
            and comparator.state is RuntimeShadowState.COMPLETED
            and comparator.report is not None
            and comparator.metrics is not None
        )
        output_valid = bool(
            runtime_output is not None
            and runtime_output.status is PlanningRuntimeOutputStatus.READY
            and runtime_output.snapshot is not None
        )
        certification_level_valid = (
            certification.level.rank
            >= self._policy.required_certification_level.rank
        )
        certification_decision_valid = (
            certification.decision is RuntimeCertificationDecision.GO
        )
        certification_gates_valid = all(
            code in gate_by_code
            and gate_by_code[code].status
            is RuntimeCertificationGateStatus.PASS
            for code in self._policy.required_gate_codes
        )
        cohort_shape_valid = (
            len(context.cohort.operational_unit_ids)
            <= self._policy.maximum_operational_units
            and context.cohort.execution_percentage
            <= self._policy.maximum_execution_percentage
        )
        cohort_evidence = context.cohort_evidence
        cohort_evidence_valid = (
            cohort_evidence.observed_operational_days
            >= self._policy.minimum_observed_operational_days
            and cohort_evidence.observed_execution_count
            >= self._policy.minimum_observed_execution_count
            and cohort_evidence.execution_success_percent
            >= self._policy.minimum_execution_success_percent
            and cohort_evidence.sev1_incident_count
            <= self._policy.maximum_sev1_incident_count
            and cohort_evidence.sev2_incident_count
            <= self._policy.maximum_sev2_incident_count
            and cohort_evidence.mixed_version_deploy_passed
        )
        cohort_scope_valid = (
            context.cohort.organization_id
            == context.scope.organization_id
            and context.scope.operational_unit_id
            in context.cohort.operational_unit_ids
        )
        feature_flag_valid = (
            context.cohort.enabled
            and context.cohort.selected_for_execution
        )
        scope_valid = self._scope_consistent(context)
        legacy_standby_valid = (
            context.legacy_available and not context.legacy_write_active
        )
        single_writer_valid = (
            not context.legacy_write_active
            and not context.runtime_write_active
            and not context.active_execution
        )
        ou_mutable = context.scope.operational_unit_id.casefold() not in {
            "*",
            "all",
            "tutte",
        }

        return (
            self._rule(
                "AUTHORITY_WRITE_ALLOWED",
                authority_valid,
                "Authority Runtime WRITE_ALLOWED valida.",
                "Authority Runtime non valida.",
                "Richiedere una Authority Decision RUNTIME attiva e scoped.",
            ),
            self._rule(
                "PUBLICATION_VALID",
                publication_valid,
                "Publication valida.",
                "Publication assente, revocata o non pubblicata.",
                "Usare una Publication PUBLISHED valida.",
            ),
            self._rule(
                "EXECUTION_INTENT_READY",
                intent_valid,
                "Execution Intent READY.",
                "Execution Intent non READY o non NORMAL.",
                "Creare un Intent READY per l'esecuzione primaria.",
            ),
            self._rule(
                "EXECUTION_ATTEMPT_READY",
                attempt_valid,
                "Execution Attempt READY_TO_EXECUTE.",
                "Execution Attempt non READY_TO_EXECUTE.",
                "Completare il gate dell'Execution Attempt.",
            ),
            self._rule(
                "CANARY_PASS",
                canary_valid,
                "Runtime Canary PASS.",
                "Runtime Canary non PASS.",
                "Completare il Canary senza failure.",
            ),
            self._rule(
                "PARITY_THRESHOLD",
                parity_valid,
                "Parity entro la soglia.",
                "Parity inferiore al 99,5%.",
                "Chiudere i mismatch e ripetere il Canary.",
            ),
            self._rule(
                "CRITICAL_MISMATCH_ZERO",
                critical_valid,
                "Critical mismatch pari a zero.",
                "Critical mismatch presente.",
                "Arrestare la promozione e risolvere ogni mismatch critico.",
            ),
            self._rule(
                "DUPLICATE_EXECUTION_ZERO",
                duplicate_valid,
                "Duplicate execution pari a zero.",
                "Duplicate execution rilevata.",
                "Riconciliare e ripetere i test di idempotenza.",
            ),
            self._rule(
                "COMPARATOR_COMPLETED",
                comparator_valid,
                "Comparator completato.",
                "Comparator non disponibile o incompleto.",
                "Completare Shadow Comparator per lo stesso scope.",
            ),
            self._rule(
                "RUNTIME_OUTPUT_READY",
                output_valid,
                "Runtime Output READY.",
                "Runtime Output non READY.",
                "Produrre uno snapshot Runtime completo e valido.",
            ),
            self._rule(
                "CERTIFICATION_LEVEL",
                certification_level_valid,
                "Certification Level sufficiente.",
                "Certification Level inferiore a Level 2.",
                "Completare la certificazione Migration Ready.",
            ),
            self._rule(
                "CERTIFICATION_DECISION",
                certification_decision_valid,
                "Certification decision GO.",
                "Certification decision NO-GO.",
                "Ottenere un record GO firmato.",
            ),
            self._rule(
                "CERTIFICATION_GATES",
                certification_gates_valid,
                "Tutti i gate obbligatori PASS.",
                "Uno o piu gate obbligatori non sono PASS.",
                "Fornire evidenza valida per tutti i dieci gate.",
            ),
            self._rule(
                "COHORT_LIMIT",
                cohort_shape_valid,
                "Coorte entro un'OU e il 5%.",
                "Coorte oltre il limite PW-9G.",
                "Ridurre la coorte a una OU e massimo 5%.",
            ),
            self._rule(
                "CANARY_EVIDENCE",
                cohort_evidence_valid,
                "Evidenza Canary PW-9G completa.",
                "Evidenza Canary PW-9G incompleta.",
                (
                    "Completare 14 giorni, 500 esecuzioni, successo 99,9%, "
                    "zero Sev-1/2 e deploy mixed-version."
                ),
            ),
            self._rule(
                "COHORT_SCOPE",
                cohort_scope_valid,
                "Scope incluso nella coorte.",
                "Scope non autorizzato dalla coorte.",
                "Usare solo organization e OU approvate.",
            ),
            self._rule(
                "COHORT_FEATURE_FLAG",
                feature_flag_valid,
                "Feature flag server-side abilita lo scope.",
                "Feature flag assente o scope non selezionato.",
                "Abilitare esplicitamente la coorte approvata.",
            ),
            self._rule(
                "SCOPE_CONSISTENT",
                scope_valid,
                "Scope coerente lungo la pipeline.",
                "Scope, Publication o fingerprint non coerenti.",
                "Ricostruire la pipeline sullo stesso scope immutabile.",
            ),
            self._rule(
                "OPERATIONAL_UNIT_MUTABLE",
                ou_mutable,
                "Operational Unit specifica.",
                "Lo scope aggregato non puo ricevere scritture.",
                "Selezionare una sola Operational Unit.",
            ),
            self._rule(
                "LEGACY_STANDBY",
                legacy_standby_valid,
                "Legacy disponibile e non writer.",
                "Legacy non disponibile oppure ancora writer.",
                "Portare Legacy in standby prima della promozione.",
            ),
            self._rule(
                "SINGLE_WRITER",
                single_writer_valid,
                "Nessun writer concorrente attivo.",
                "Writer o esecuzione concorrente rilevati.",
                "Bloccare e riconciliare lo scope prima di procedere.",
            ),
        )

    def _canary_rules(
        self,
        context: RuntimePrimaryEvaluationContext,
    ) -> tuple[RuntimePrimaryValidationRule, ...]:
        canary = context.canary
        canary_valid = bool(
            canary is not None
            and canary.session.status is RuntimeCanaryStatus.FINISHED
            and canary.report.decision is RuntimeCanaryDecision.PASS
        )
        no_writers = (
            not context.legacy_write_active
            and not context.runtime_write_active
            and not context.active_execution
        )
        return (
            self._rule(
                "CANARY_PASS",
                canary_valid,
                "Runtime Canary PASS.",
                "Runtime Canary non PASS.",
                "Mantenere Runtime in osservazione.",
            ),
            self._rule(
                "COHORT_SCOPE",
                self._cohort_scope_valid(context),
                "Scope incluso nella coorte.",
                "Scope non autorizzato dalla coorte.",
                "Usare la coorte PW-9G approvata.",
            ),
            self._rule(
                "NO_OPERATIONAL_WRITE",
                no_writers,
                "Canary privo di scritture operative.",
                "Una scrittura e attiva durante il Canary.",
                "Arrestare il Canary e riconciliare lo scope.",
            ),
            self._rule(
                "SCOPE_CONSISTENT",
                self._scope_consistent(context),
                "Scope coerente.",
                "Scope Canary incoerente.",
                "Ricostruire il contesto sullo stesso scope.",
            ),
        )

    def _rollback_rules(
        self,
        context: RuntimePrimaryEvaluationContext,
    ) -> tuple[RuntimePrimaryValidationRule, ...]:
        decision = context.authority.decision
        authority_valid = bool(
            context.authority.state
            is AuthorityResolutionState.WRITE_ALLOWED
            and decision is not None
            and decision.mode is AuthorityDecisionMode.LEGACY
        )
        intent_valid = (
            context.intent.status is ExecutionIntentStatus.READY
            and context.intent.scope.execution_mode
            is ExecutionIntentMode.ROLLBACK
        )
        return (
            self._rule(
                "ROLLBACK_AUTHORITY",
                authority_valid,
                "Authority LEGACY WRITE_ALLOWED valida.",
                "Authority di rollback non valida.",
                "Registrare il cambio di Authority verso Legacy.",
            ),
            self._rule(
                "ROLLBACK_INTENT",
                intent_valid,
                "Rollback Intent READY.",
                "Rollback Intent non READY.",
                "Creare un Intent ROLLBACK autorizzato.",
            ),
            self._rule(
                "ROLLBACK_AUTHORIZED",
                context.rollback_authorized,
                "Rollback approvato.",
                "Rollback non approvato.",
                "Completare il workflow di approvazione.",
            ),
            self._rule(
                "RECONCILIATION_COMPLETE",
                context.reconciliation_complete,
                "Reconciliation completata.",
                "Reconciliation incompleta.",
                "Determinare l'outcome del tentativo corrente.",
            ),
            self._rule(
                "NO_ACTIVE_EXECUTION",
                not context.active_execution,
                "Nessuna esecuzione attiva.",
                "Esecuzione ancora attiva o indeterminata.",
                "Completare o compensare l'esecuzione prima del fallback.",
            ),
            self._rule(
                "RUNTIME_WRITE_STOPPED",
                not context.runtime_write_active,
                "Nuove scritture Runtime bloccate.",
                "Runtime writer ancora attivo.",
                "Bloccare Runtime prima di attivare Legacy.",
            ),
            self._rule(
                "LEGACY_AVAILABLE",
                context.legacy_available,
                "Legacy disponibile.",
                "Legacy non disponibile.",
                "Ripristinare il percorso Legacy verificato.",
            ),
            self._rule(
                "STATE_PRESERVATION",
                context.state_preservation_verified,
                "Preservazione dello stato verificata.",
                "Preservazione dello stato non verificata.",
                "Confrontare e riconciliare lo stato prima del fallback.",
            ),
            self._rule(
                "COHORT_SCOPE",
                self._cohort_scope_valid(context),
                "Rollback limitato alla coorte.",
                "Rollback fuori dalla coorte autorizzata.",
                "Limitare il rollback allo scope interessato.",
            ),
            self._rule(
                "SCOPE_CONSISTENT",
                self._scope_consistent(context),
                "Scope di rollback coerente.",
                "Scope di rollback incoerente.",
                "Usare lo stesso scope e la stessa Publication.",
            ),
        )

    def _cohort_scope_valid(
        self,
        context: RuntimePrimaryEvaluationContext,
    ) -> bool:
        return (
            context.cohort.organization_id
            == context.scope.organization_id
            and context.scope.operational_unit_id
            in context.cohort.operational_unit_ids
        )

    @staticmethod
    def _scope_consistent(
        context: RuntimePrimaryEvaluationContext,
    ) -> bool:
        scope = context.scope
        authority_scope = context.authority.scope
        publication = context.publication
        intent = context.intent
        if authority_scope.identity != scope.identity:
            return False
        if (
            publication.organization_id != scope.organization_id
            or publication.operational_unit_id
            != scope.operational_unit_id
            or publication.planning_date != scope.planning_date
            or intent.scope.operational_identity != scope.identity
            or intent.scope.publication_id != publication.publication_id
            or intent.scope.publication_version
            != publication.publication_version
            or intent.publication_fingerprint != publication.fingerprint
        ):
            return False
        if context.attempt is not None and (
            context.attempt.scope.organization_id
            != scope.organization_id
            or context.attempt.scope.operational_unit_id
            != scope.operational_unit_id
            or context.attempt.scope.planning_date != scope.planning_date
            or context.attempt.scope.timezone != scope.timezone
            or context.attempt.scope.execution_intent_id
            != intent.intent_id
            or context.attempt.publication_id
            != publication.publication_id
            or context.attempt.publication_version
            != publication.publication_version
            or context.attempt.publication_fingerprint
            != publication.fingerprint
            or context.attempt.authority_decision_id
            != intent.authority_decision_id
            or context.attempt.fencing_token != intent.fencing_token
        ):
            return False
        if context.canary is not None and (
            context.canary.session.scope.identity != scope.identity
            or context.canary.session.publication_id
            != publication.publication_id
            or context.canary.session.publication_version
            != publication.publication_version
        ):
            return False
        if context.comparator is not None and (
            context.comparator.report is None
            or context.comparator.report.operational_unit
            != scope.operational_unit_id
            or context.comparator.report.planning_date
            != scope.planning_date
            or context.comparator.report.publication_version
            != publication.publication_version
        ):
            return False
        if context.runtime_output is not None:
            snapshot = context.runtime_output.snapshot
            if snapshot is None:
                return False
            output = snapshot.output
            if (
                output.scope != scope
                or output.publication_version
                != publication.publication_version
                or output.metadata.publication_id
                != publication.publication_id
                or output.metadata.publication_fingerprint
                != publication.fingerprint
            ):
                return False
        return True
