from app.domain.legacy_retirement.models import (
    LegacyRetirementCheck,
    LegacyRetirementContext,
    LegacyRetirementGateSummary,
    LegacyRetirementPolicy,
    LegacyRetirementState,
    LegacyRetirementValidationResult,
)
from app.domain.runtime_primary import (
    RuntimeCertificationDecision,
    RuntimeCertificationGateStatus,
    RuntimePrimaryStatus,
)


class LegacyRetirementValidator:
    def __init__(self, policy: LegacyRetirementPolicy) -> None:
        self._policy = policy

    @staticmethod
    def _check(
        code: str,
        passed: bool,
        success: str,
        failure: str,
        remediation_hint: str,
    ) -> LegacyRetirementCheck:
        return LegacyRetirementCheck(
            code=code,
            passed=passed,
            reason=success if passed else failure,
            remediation_hint=None if passed else remediation_hint,
        )

    def validate(
        self,
        context: LegacyRetirementContext,
    ) -> LegacyRetirementValidationResult:
        gates = self._gate_summary(context)
        certification = context.certification
        stable = (
            context.runtime_primary_stable
            and context.runtime_stable_days
            >= self._policy.minimum_runtime_stable_days
            and context.runtime_execution_count
            >= self._policy.minimum_runtime_execution_count
            and context.runtime_success_percent
            >= self._policy.minimum_runtime_success_percent
            and context.all_operational_units_enabled
            and context.sev1_incident_count
            <= self._policy.maximum_sev1_incidents
            and context.sev2_incident_count
            <= self._policy.maximum_sev2_incidents
        )
        legacy_preserved = (
            context.legacy_available
            and context.legacy_observable
            and context.legacy_recoverable
            and context.legacy_code_present
        )
        checklist = (
            self._check(
                "RUNTIME_PRIMARY_CERTIFIED",
                context.runtime_primary_status is RuntimePrimaryStatus.PRIMARY,
                "Runtime Primary certificato.",
                "Runtime Primary non certificato.",
                "Completare la promozione Runtime certificata.",
            ),
            self._check(
                "PRODUCTION_CERTIFICATION",
                (
                    certification.level.rank
                    >= self._policy.required_certification_level.rank
                    and certification.decision
                    is RuntimeCertificationDecision.GO
                ),
                "Production Certification valida.",
                "Production Certification insufficiente o NO-GO.",
                "Ottenere almeno Level 3 con decisione GO.",
            ),
            self._check(
                "MANDATORY_GATES",
                gates.status is RuntimeCertificationGateStatus.PASS,
                "Tutti i gate obbligatori PASS.",
                "Uno o piu gate obbligatori non sono PASS.",
                "Chiudere FAIL, WARNING e gate mancanti.",
            ),
            self._check(
                "NO_OPEN_BLOCKERS",
                not context.open_blockers,
                "Nessun blocker aperto.",
                "Sono presenti blocker aperti.",
                "Chiudere e verificare tutti i blocker.",
            ),
            self._check(
                "CRITICAL_MISMATCH_ZERO",
                (
                    context.critical_mismatch_count
                    <= self._policy.maximum_critical_mismatch
                ),
                "Critical mismatch pari a zero.",
                "Critical mismatch presente.",
                "Risolvere ogni mismatch critico.",
            ),
            self._check(
                "DUPLICATE_EXECUTION_ZERO",
                (
                    context.duplicate_execution_count
                    <= self._policy.maximum_duplicate_execution
                ),
                "Duplicate execution pari a zero.",
                "Duplicate execution rilevata.",
                "Riconciliare e ripetere i test di idempotenza.",
            ),
            self._check(
                "ROLLBACK_VERIFIED",
                context.rollback_verified and context.rollback_available,
                "Rollback verificato e disponibile.",
                "Rollback non verificato o non disponibile.",
                "Completare un rollback drill production-like.",
            ),
            self._check(
                "AUDIT_COMPLETE",
                context.audit_complete,
                "Audit completo.",
                "Audit incompleto.",
                "Completare audit e correlazione end-to-end.",
            ),
            self._check(
                "CANARY_COMPLETE",
                context.canary_complete,
                "Canary completato.",
                "Canary non completato.",
                "Completare la campagna Canary certificata.",
            ),
            self._check(
                "RUNTIME_PRIMARY_STABLE",
                stable,
                "Runtime Primary stabile su tutte le OU.",
                "Stabilita Runtime insufficiente.",
                (
                    "Completare 30 giorni, 500 esecuzioni, successo 99,9%, "
                    "zero Sev-1/2 e rollout 100%."
                ),
            ),
            self._check(
                "LEGACY_PRESERVED",
                legacy_preserved,
                "Legacy disponibile, osservabile e recuperabile.",
                "Legacy non e integralmente recuperabile.",
                "Ripristinare codice, osservabilita e recovery Legacy.",
            ),
            self._check(
                "LEGACY_STANDBY",
                context.observed_state is LegacyRetirementState.STANDBY,
                "Legacy in standby.",
                "Legacy ancora attivo.",
                "Mantenere Legacy disponibile ma fuori dal writer primario.",
            ),
        )
        return LegacyRetirementValidationResult(
            allowed=all(item.passed for item in checklist),
            checklist=checklist,
            gates=gates,
            evaluated_at=context.evaluated_at,
        )

    def _gate_summary(
        self,
        context: LegacyRetirementContext,
    ) -> LegacyRetirementGateSummary:
        gate_by_code = {
            gate.code: gate for gate in context.certification.gates
        }
        required = self._policy.required_gate_codes
        statuses = tuple(
            gate_by_code[code].status
            for code in required
            if code in gate_by_code
        )
        missing = tuple(code for code in required if code not in gate_by_code)
        fail_count = sum(
            status is RuntimeCertificationGateStatus.FAIL
            for status in statuses
        )
        warning_count = sum(
            status is RuntimeCertificationGateStatus.WARNING
            for status in statuses
        )
        pass_count = sum(
            status is RuntimeCertificationGateStatus.PASS
            for status in statuses
        )
        if fail_count or missing:
            status = RuntimeCertificationGateStatus.FAIL
        elif warning_count:
            status = RuntimeCertificationGateStatus.WARNING
        else:
            status = RuntimeCertificationGateStatus.PASS
        return LegacyRetirementGateSummary(
            required_count=len(required),
            pass_count=pass_count,
            warning_count=warning_count,
            fail_count=fail_count,
            missing_codes=missing,
            status=status,
        )
