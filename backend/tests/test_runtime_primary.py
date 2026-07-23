from statistics import median
from time import perf_counter

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.api.dependencies.runtime_primary import get_runtime_primary
from app.core.database import db_session
from app.domain.execution_attempt import ExecutionAttemptStatus
from app.domain.execution_intent import (
    ExecutionIntentMode,
    ExecutionIntentStatus,
    ExecutionPublicationStatus,
)
from app.domain.planning_runtime import PlanningRuntimeScope
from app.domain.runtime_authority import (
    AuthorityDecisionMode,
    AuthorityResolutionState,
)
from app.domain.runtime_primary import (
    LegacyFallbackResult,
    RuntimeCertificationDecision,
    RuntimeCertificationGate,
    RuntimeCertificationGateStatus,
    RuntimeCertificationLevel,
    RuntimeCertificationSnapshot,
    RuntimePrimaryCohort,
    RuntimePrimaryCohortEvidence,
    RuntimePrimaryDecision,
    RuntimePrimaryEvaluationContext,
    RuntimePrimaryMode,
    RuntimePrimaryOutcome,
    RuntimePrimaryPolicy,
    RuntimePrimaryService,
    RuntimePrimaryStatus,
    RuntimePrimaryValidator,
    RuntimePrimaryWriteResult,
)
from app.main import app
from app.runtime.primary import RuntimePrimaryRuntime
from test_execution_intent import NOW, _authority
from test_runtime_canary import (
    _canary_context,
    _service as canary_service,
)


class RecordingRuntimeWriter:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.calls = []

    def write(self, context):
        self.calls.append(context)
        if self.fail:
            raise RuntimeError("Synthetic writer failure.")
        return RuntimePrimaryWriteResult(
            committed=True,
            runtime_write_count=1,
            duplicate_execution=0,
            latency_ms=1.2,
            outcome_reference="runtime-write-a",
            fencing_token=context.intent.fencing_token,
        )


class RecordingLegacyFallback:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.calls = []

    def activate(self, context):
        self.calls.append(context)
        if self.fail:
            raise RuntimeError("Synthetic fallback failure.")
        return LegacyFallbackResult(
            activated=True,
            legacy_fallback_count=1,
            state_preserved=True,
            latency_ms=1.4,
            outcome_reference="legacy-fallback-a",
        )


class FixedRuntimePrimaryProvider:
    def __init__(self, context) -> None:
        self.context = context

    def get(self, *, scope, publication_id, publication_version):
        return self.context


def _certification(
    *,
    failed_gate: str | None = None,
) -> RuntimeCertificationSnapshot:
    gates = tuple(
        RuntimeCertificationGate(
            code=f"GATE_{index}",
            status=(
                RuntimeCertificationGateStatus.FAIL
                if failed_gate == f"GATE_{index}"
                else RuntimeCertificationGateStatus.PASS
            ),
            evidence_reference=f"evidence://gate-{index}",
        )
        for index in range(1, 11)
    )
    return RuntimeCertificationSnapshot(
        level=RuntimeCertificationLevel.LEVEL_2,
        decision=(
            RuntimeCertificationDecision.NO_GO
            if failed_gate
            else RuntimeCertificationDecision.GO
        ),
        gates=gates,
        certified_at=NOW,
        record_reference="certification://pw-9g",
    )


def _cohort(
    *,
    selected: bool = True,
    operational_unit_ids: tuple[str, ...] = ("unit-a",),
) -> RuntimePrimaryCohort:
    return RuntimePrimaryCohort(
        cohort_id="cohort-pw-9g-a",
        organization_id="organization-a",
        operational_unit_ids=operational_unit_ids,
        execution_percentage=5.0,
        feature_flag_key="runtime-primary.pw-9g",
        feature_flag_version="1",
        enabled=True,
        selected_for_execution=selected,
    )


def _cohort_evidence(
    *,
    operational_days: int = 14,
    execution_count: int = 500,
    success_percent: float = 99.9,
) -> RuntimePrimaryCohortEvidence:
    return RuntimePrimaryCohortEvidence(
        observed_operational_days=operational_days,
        observed_execution_count=execution_count,
        execution_success_percent=success_percent,
        sev1_incident_count=0,
        sev2_incident_count=0,
        mixed_version_deploy_passed=True,
    )


def _context(
    *,
    legacy_changes=None,
    certification=None,
    cohort=None,
    cohort_evidence=None,
    duplicate_execution: int = 0,
) -> RuntimePrimaryEvaluationContext:
    canary_context = _canary_context(legacy_changes=legacy_changes)
    if duplicate_execution:
        shadow = canary_context.shadow_result
        canary_context = canary_context.model_copy(
            update={
                "shadow_result": shadow.model_copy(
                    update={
                        "metrics": shadow.metrics.model_copy(
                            update={
                                "duplicate_execution": duplicate_execution,
                            }
                        )
                    }
                )
            }
        )
    canary = canary_service().evaluate(canary_context)
    intent = canary_context.intent
    scope = PlanningRuntimeScope(
        organization_id=intent.scope.organization_id,
        operational_unit_id=intent.scope.operational_unit_id,
        planning_date=intent.scope.planning_date,
        timezone=intent.scope.timezone,
    )
    return RuntimePrimaryEvaluationContext(
        scope=scope,
        requested_mode=RuntimePrimaryMode.PRIMARY,
        authority=canary_context.authority,
        publication=canary_context.publication,
        intent=intent,
        attempt=canary_context.attempt,
        canary=canary,
        comparator=canary_context.shadow_result,
        runtime_output=canary_context.producer_result,
        certification=certification or _certification(),
        cohort=cohort or _cohort(),
        cohort_evidence=cohort_evidence or _cohort_evidence(),
        legacy_available=True,
        legacy_write_active=False,
        runtime_write_active=False,
        active_execution=False,
        legacy_latency_ms=100.0,
        evaluated_at=NOW,
    )


def _service(*, writer=None, fallback=None):
    policy = RuntimePrimaryPolicy()
    return RuntimePrimaryService(
        validator=RuntimePrimaryValidator(policy),
        writer=writer or RecordingRuntimeWriter(),
        fallback=fallback or RecordingLegacyFallback(),
        clock=lambda: NOW,
    )


def _endpoint_params():
    return {
        "organization_id": "organization-a",
        "operational_unit_id": "unit-a",
        "planning_date": NOW.date().isoformat(),
        "timezone": "Europe/Rome",
        "publication_id": "publication-a",
        "publication_version": 1,
    }


def _diagnostic_codes(report):
    return {item.code for item in report.diagnostics.items}


def test_valid_promotion_uses_runtime_as_single_writer_for_cohort():
    writer = RecordingRuntimeWriter()
    fallback = RecordingLegacyFallback()

    report = _service(writer=writer, fallback=fallback).apply(_context())

    assert report.status is RuntimePrimaryStatus.PRIMARY
    assert report.decision is RuntimePrimaryDecision.PROMOTED
    assert report.outcome is RuntimePrimaryOutcome.RUNTIME_WRITE_COMMITTED
    assert report.metrics.runtime_write_count == 1
    assert report.metrics.legacy_fallback_count == 0
    assert report.metrics.parity_percent == 100
    assert report.metrics.critical_mismatch == 0
    assert report.metrics.duplicate_execution == 0
    assert report.metrics.canary_observation_days == 14
    assert report.metrics.canary_execution_count == 500
    assert len(writer.calls) == 1
    assert fallback.calls == []


def test_certification_gate_failure_denies_promotion_fail_closed():
    writer = RecordingRuntimeWriter()
    context = _context(certification=_certification(failed_gate="GATE_4"))

    report = _service(writer=writer).apply(context)

    assert report.status is RuntimePrimaryStatus.REJECTED
    assert report.outcome is RuntimePrimaryOutcome.FAILED_CLOSED
    assert "CERTIFICATION_GATES" in _diagnostic_codes(report)
    assert writer.calls == []


def test_authority_no_write_denies_promotion():
    writer = RecordingRuntimeWriter()
    context = _context()
    authority = _authority(
        scope=context.intent.scope,
        state=AuthorityResolutionState.NO_WRITE,
    )

    report = _service(writer=writer).apply(
        context.model_copy(update={"authority": authority})
    )

    assert report.status is RuntimePrimaryStatus.REJECTED
    assert "AUTHORITY_WRITE_ALLOWED" in _diagnostic_codes(report)
    assert writer.calls == []


def test_parity_below_threshold_denies_promotion():
    writer = RecordingRuntimeWriter()
    context = _context(
        legacy_changes={"resources": ("resource-a", "resource-c")}
    )

    report = _service(writer=writer).apply(context)

    assert report.status is RuntimePrimaryStatus.REJECTED
    assert report.metrics.parity_percent < 99.5
    assert "PARITY_THRESHOLD" in _diagnostic_codes(report)
    assert writer.calls == []


@pytest.mark.parametrize(
    ("component", "diagnostic"),
    [
        ("publication", "PUBLICATION_VALID"),
        ("intent", "EXECUTION_INTENT_READY"),
        ("attempt", "EXECUTION_ATTEMPT_READY"),
    ],
)
def test_pipeline_gate_failure_denies_promotion(component, diagnostic):
    writer = RecordingRuntimeWriter()
    context = _context()
    if component == "publication":
        context = context.model_copy(
            update={
                "publication": context.publication.model_copy(
                    update={
                        "status": ExecutionPublicationStatus.REVOKED,
                    }
                )
            }
        )
    elif component == "intent":
        context = context.model_copy(
            update={
                "intent": context.intent.model_copy(
                    update={"status": ExecutionIntentStatus.CANCELLED}
                )
            }
        )
    else:
        context = context.model_copy(
            update={
                "attempt": context.attempt.model_copy(
                    update={"status": ExecutionAttemptStatus.ABORTED}
                )
            }
        )

    report = _service(writer=writer).apply(context)

    assert report.status is RuntimePrimaryStatus.REJECTED
    assert diagnostic in _diagnostic_codes(report)
    assert writer.calls == []


def test_duplicate_execution_denies_promotion():
    writer = RecordingRuntimeWriter()
    context = _context(duplicate_execution=1)

    report = _service(writer=writer).apply(context)

    assert report.status is RuntimePrimaryStatus.REJECTED
    assert report.metrics.duplicate_execution == 1
    assert "DUPLICATE_EXECUTION_ZERO" in _diagnostic_codes(report)
    assert writer.calls == []


def test_incomplete_canary_evidence_denies_promotion():
    writer = RecordingRuntimeWriter()
    context = _context(
        cohort_evidence=_cohort_evidence(
            operational_days=13,
            execution_count=499,
            success_percent=99.8,
        )
    )

    report = _service(writer=writer).apply(context)

    assert report.status is RuntimePrimaryStatus.REJECTED
    assert "CANARY_EVIDENCE" in _diagnostic_codes(report)
    assert writer.calls == []


def test_explicit_rollback_reactivates_legacy_after_reconciliation():
    writer = RecordingRuntimeWriter()
    fallback = RecordingLegacyFallback()
    context = _context()
    authority = context.authority.model_copy(
        update={
            "decision": context.authority.decision.model_copy(
                update={"mode": AuthorityDecisionMode.LEGACY}
            )
        }
    )
    intent = context.intent.model_copy(
        update={
            "scope": context.intent.scope.model_copy(
                update={"execution_mode": ExecutionIntentMode.ROLLBACK}
            )
        }
    )
    rollback = context.model_copy(
        update={
            "requested_mode": RuntimePrimaryMode.ROLLBACK,
            "authority": authority,
            "intent": intent,
            "rollback_authorized": True,
            "reconciliation_complete": True,
            "state_preservation_verified": True,
        }
    )

    report = _service(writer=writer, fallback=fallback).apply(rollback)

    assert report.status is RuntimePrimaryStatus.ROLLED_BACK
    assert report.decision is RuntimePrimaryDecision.FALLBACK
    assert report.outcome is (
        RuntimePrimaryOutcome.LEGACY_FALLBACK_ACTIVATED
    )
    assert report.metrics.rollback_count == 1
    assert report.metrics.legacy_fallback_count == 1
    assert writer.calls == []
    assert len(fallback.calls) == 1


def test_runtime_write_failure_does_not_trigger_automatic_fallback():
    writer = RecordingRuntimeWriter(fail=True)
    fallback = RecordingLegacyFallback()

    report = _service(writer=writer, fallback=fallback).apply(_context())

    assert report.status is RuntimePrimaryStatus.ERROR
    assert report.decision is RuntimePrimaryDecision.DENY
    assert report.outcome is RuntimePrimaryOutcome.ERROR
    assert "RUNTIME_PRIMARY_WRITE_FAILED" in _diagnostic_codes(report)
    assert len(writer.calls) == 1
    assert fallback.calls == []


def test_unauthorized_cohort_has_no_effect_outside_selected_scope():
    writer = RecordingRuntimeWriter()
    context = _context(cohort=_cohort(selected=False))

    report = _service(writer=writer).apply(context)

    assert report.status is RuntimePrimaryStatus.REJECTED
    assert "COHORT_FEATURE_FLAG" in _diagnostic_codes(report)
    assert writer.calls == []


def test_primary_report_is_deeply_immutable():
    report = _service().apply(_context())

    with pytest.raises(ValidationError):
        report.status = RuntimePrimaryStatus.REJECTED
    with pytest.raises(ValidationError):
        report.metrics.runtime_write_count = 2


def test_read_only_assessment_exposes_eligibility_without_writing():
    writer = RecordingRuntimeWriter()
    fallback = RecordingLegacyFallback()
    context = _context()

    report = _service(writer=writer, fallback=fallback).assess(context)

    assert report.status is RuntimePrimaryStatus.READY_TO_PROMOTE
    assert report.decision is RuntimePrimaryDecision.ELIGIBLE
    assert report.outcome is RuntimePrimaryOutcome.NO_EFFECT
    assert writer.calls == []
    assert fallback.calls == []


def test_default_endpoint_reports_current_certification_no_go():
    tables = ("plannings", "assignments", "planning_publications")
    with db_session() as conn:
        before = {
            table: conn.execute(
                f"SELECT COUNT(*) AS total FROM {table}"
            ).fetchone()["total"]
            for table in tables
        }

    response = TestClient(app).get(
        "/api/runtime/primary",
        params=_endpoint_params(),
    )

    with db_session() as conn:
        after = {
            table: conn.execute(
                f"SELECT COUNT(*) AS total FROM {table}"
            ).fetchone()["total"]
            for table in tables
        }
    assert response.status_code == 200
    assert response.json()["report"]["status"] == "DISABLED"
    assert response.json()["report"]["decision"] == "DENY"
    assert response.json()["report"]["diagnostics"]["items"][0][
        "code"
    ] == "READINESS_CERTIFICATION_NO_GO"
    assert after == before


def test_endpoint_with_valid_context_remains_read_only():
    writer = RecordingRuntimeWriter()
    fallback = RecordingLegacyFallback()
    context = _context()
    runtime = RuntimePrimaryRuntime(
        service=_service(writer=writer, fallback=fallback),
        provider=FixedRuntimePrimaryProvider(context),
    )
    app.dependency_overrides[get_runtime_primary] = lambda: runtime
    try:
        response = TestClient(app).get(
            "/api/runtime/primary",
            params=_endpoint_params(),
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["report"]["status"] == "READY_TO_PROMOTE"
    assert response.json()["report"]["outcome"] == "NO_EFFECT"
    assert writer.calls == []
    assert fallback.calls == []


def test_endpoint_rejects_invalid_timezone_without_stack_trace():
    params = _endpoint_params()
    params["timezone"] = "invalid/timezone"

    response = TestClient(app).get(
        "/api/runtime/primary",
        params=params,
    )

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == (
        "INVALID_RUNTIME_PRIMARY_SCOPE"
    )
    assert "traceback" not in response.text.lower()


def test_openapi_exposes_exactly_one_read_only_primary_operation():
    operation = app.openapi()["paths"]["/api/runtime/primary"]

    assert set(operation) == {"get"}


def test_primary_validation_meets_latency_target():
    context = _context()
    service = _service()
    samples = []

    for _ in range(200):
        started = perf_counter()
        report = service.assess(context)
        samples.append((perf_counter() - started) * 1_000)

    assert median(samples) < 15
    assert report.metrics.runtime_write_count == 0
    assert report.metrics.legacy_fallback_count == 0
