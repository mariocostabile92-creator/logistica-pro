from datetime import timedelta
from statistics import median
from time import perf_counter

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.api.dependencies.runtime_canary import get_runtime_canary
from app.core.database import db_session
from app.domain.execution_attempt import ExecutionAttemptStatus
from app.domain.runtime_authority import AuthorityResolutionState
from app.domain.planning_runtime import PlanningRuntimeOutputFormatter
from app.domain.runtime_canary import (
    RuntimeCanaryDecision,
    RuntimeCanaryEvaluationContext,
    RuntimeCanaryPolicy,
    RuntimeCanaryService,
    RuntimeCanarySession,
    RuntimeCanaryStatus,
    RuntimeCanaryValidator,
)
from app.domain.runtime_shadow import (
    PlanningComparator,
    RuntimeShadowService,
)
from app.main import app
from app.runtime.canary import RuntimeCanaryRuntime
from app.runtime.planning_output import PlanningRuntimeShadowBridge
from test_execution_intent import NOW, _authority
from test_planning_runtime_output import (
    _context as runtime_context,
    _legacy_shadow,
    _service as producer_service,
)


def _service(*, elapsed_ms: float = 4.0) -> RuntimeCanaryService:
    return RuntimeCanaryService(
        policy=RuntimeCanaryPolicy(),
        validator=RuntimeCanaryValidator(),
        clock=lambda: NOW + timedelta(milliseconds=elapsed_ms),
    )


def _comparison(*, legacy_changes=None):
    context = runtime_context()
    ready_attempt = context.attempt.model_copy(
        update={"status": ExecutionAttemptStatus.READY_TO_EXECUTE}
    )
    context = context.model_copy(update={"attempt": ready_attempt})
    produced = producer_service().produce(context)
    legacy = _legacy_shadow(context.source, produced.snapshot.output)
    if legacy_changes:
        legacy = legacy.model_copy(update=legacy_changes)
    bridge = PlanningRuntimeShadowBridge(
        producer_service=producer_service(),
        shadow_service=RuntimeShadowService(
            comparator=PlanningComparator(clock=lambda: NOW),
            clock=lambda: NOW,
        ),
        formatter=PlanningRuntimeOutputFormatter(),
    )
    return context, bridge.compare(context=context, legacy=legacy)


def _canary_context(*, legacy_changes=None, legacy_latency_ms=100.0):
    production, comparison = _comparison(legacy_changes=legacy_changes)
    authority_decision = str(production.authority.decision.decision_id)
    session = RuntimeCanarySession(
        session_id="canary-session-a",
        organization_id=production.intent.scope.organization_id,
        operational_unit_id=production.intent.scope.operational_unit_id,
        planning_date=production.intent.scope.planning_date,
        timezone=production.intent.scope.timezone,
        started_at=NOW,
        authority_decision=authority_decision,
        publication_id=production.source.publication.publication_id,
        publication_version=(
            production.source.publication.publication_version
        ),
    )
    return RuntimeCanaryEvaluationContext(
        session=session,
        authority=production.authority,
        intent=production.intent,
        attempt=production.attempt,
        publication=production.source.publication,
        producer_result=comparison.producer,
        shadow_result=comparison.shadow,
        legacy_latency_ms=legacy_latency_ms,
    )


def _codes(result):
    return {item.code for item in result.report.diagnostics.items}


def test_valid_canary_finishes_with_informational_pass():
    result = _service().evaluate(_canary_context())

    assert result.session.status is RuntimeCanaryStatus.FINISHED
    assert result.report.decision is RuntimeCanaryDecision.PASS
    assert result.report.metrics.parity_percent == 100
    assert result.report.metrics.critical_mismatch == 0
    assert result.report.metrics.duplicate_execution == 0
    assert result.report.metrics.authority_conflict == 0
    assert result.status_history == (
        RuntimeCanaryStatus.CREATED,
        RuntimeCanaryStatus.RUNNING,
        RuntimeCanaryStatus.OBSERVING,
        RuntimeCanaryStatus.FINISHED,
    )
    assert "nessuna promozione automatica" in (
        result.report.diagnostics.items[-1].message
    )


def test_authority_no_write_aborts_fail_closed():
    context = _canary_context()
    authority = _authority(
        scope=context.intent.scope,
        state=AuthorityResolutionState.NO_WRITE,
    )

    result = _service().evaluate(
        context.model_copy(update={"authority": authority})
    )

    assert result.session.status is RuntimeCanaryStatus.ABORTED
    assert result.report.decision is RuntimeCanaryDecision.FAIL
    assert "AUTHORITY_INVALID" in _codes(result)


def test_parity_below_threshold_finishes_with_fail():
    context = _canary_context(
        legacy_changes={"resources": ("resource-a", "resource-c")}
    )

    result = _service().evaluate(context)

    assert result.session.status is RuntimeCanaryStatus.FINISHED
    assert result.report.decision is RuntimeCanaryDecision.FAIL
    assert result.report.metrics.parity_percent < 99.5
    parity = next(
        item for item in result.report.criteria if item.code == "PARITY"
    )
    assert parity.passed is False


def test_critical_mismatch_produces_fail():
    context = _canary_context(legacy_changes={"fingerprint": "e" * 64})

    result = _service().evaluate(context)

    assert result.report.decision is RuntimeCanaryDecision.FAIL
    assert result.report.metrics.critical_mismatch == 1
    assert any(
        not item.passed
        for item in result.report.criteria
        if item.code == "CRITICAL_MISMATCH"
    )


def test_duplicate_execution_metric_produces_fail():
    context = _canary_context()
    shadow = context.shadow_result
    duplicate_metrics = shadow.metrics.model_copy(
        update={"duplicate_execution": 1}
    )
    context = context.model_copy(
        update={
            "shadow_result": shadow.model_copy(
                update={"metrics": duplicate_metrics}
            )
        }
    )

    result = _service().evaluate(context)

    assert result.report.metrics.duplicate_execution == 1
    assert result.report.decision is RuntimeCanaryDecision.FAIL


@pytest.mark.parametrize(
    ("changes", "diagnostic"),
    [
        (
            {"comparator_available": False, "shadow_result": None},
            "COMPARATOR_NOT_AVAILABLE",
        ),
        (
            {"producer_available": False, "producer_result": None},
            "PRODUCER_NOT_AVAILABLE",
        ),
    ],
)
def test_missing_pipeline_component_aborts(changes, diagnostic):
    result = _service().evaluate(
        _canary_context().model_copy(update=changes)
    )

    assert result.session.status is RuntimeCanaryStatus.ABORTED
    assert result.report.decision is RuntimeCanaryDecision.FAIL
    assert diagnostic in _codes(result)


def test_canary_contract_and_nested_report_are_immutable():
    result = _service().evaluate(_canary_context())

    with pytest.raises(ValidationError):
        result.session.status = RuntimeCanaryStatus.ABORTED
    with pytest.raises(ValidationError):
        result.report.metrics.parity_percent = 0


def test_canary_does_not_write_operational_tables():
    tables = ("plannings", "assignments", "planning_publications")
    with db_session() as conn:
        before = {
            table: conn.execute(
                f"SELECT COUNT(*) AS total FROM {table}"
            ).fetchone()["total"]
            for table in tables
        }

    _service().evaluate(_canary_context())

    with db_session() as conn:
        after = {
            table: conn.execute(
                f"SELECT COUNT(*) AS total FROM {table}"
            ).fetchone()["total"]
            for table in tables
        }
    assert after == before


class FixedCanaryProvider:
    def __init__(self, context):
        self.context = context

    def get(self, *, scope, publication_id, publication_version):
        return self.context


def _runtime(context) -> RuntimeCanaryRuntime:
    return RuntimeCanaryRuntime(
        service=_service(),
        provider=FixedCanaryProvider(context),
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


def test_read_only_endpoint_returns_canary_report_under_payload_target():
    app.dependency_overrides[get_runtime_canary] = lambda: _runtime(
        _canary_context()
    )
    try:
        response = TestClient(app).get(
            "/api/runtime/canary",
            params=_endpoint_params(),
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["session"]["status"] == "FINISHED"
    assert response.json()["report"]["decision"] == "PASS"
    assert len(response.content) < 5 * 1024


def test_endpoint_fails_closed_without_a_resolvable_canary_context():
    response = TestClient(app).get(
        "/api/runtime/canary",
        params=_endpoint_params(),
    )

    assert response.status_code == 200
    assert response.json()["session"]["status"] == "ABORTED"
    assert response.json()["report"]["decision"] == "FAIL"
    assert response.json()["report"]["diagnostics"]["items"][0][
        "code"
    ] == "CANARY_CONTEXT_NOT_AVAILABLE"


def test_endpoint_rejects_invalid_timezone_without_stack_trace():
    params = _endpoint_params()
    params["timezone"] = "invalid/timezone"

    response = TestClient(app).get(
        "/api/runtime/canary",
        params=params,
    )

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == (
        "INVALID_RUNTIME_CANARY_SCOPE"
    )
    assert "traceback" not in response.text.lower()


def test_openapi_exposes_exactly_one_read_only_canary_operation():
    operation = app.openapi()["paths"]["/api/runtime/canary"]

    assert set(operation) == {"get"}


def test_canary_meets_latency_and_overhead_targets():
    context = _canary_context(legacy_latency_ms=100.0)
    service = _service()
    samples = []

    for _ in range(200):
        started = perf_counter()
        result = service.evaluate(context)
        samples.append((perf_counter() - started) * 1_000)

    assert median(samples) < 15
    assert result.report.metrics.comparator_latency_ms < 50
    assert result.report.metrics.canary_overhead_percent < 5


def test_overhead_above_target_is_reported_without_automatic_action():
    result = _service().evaluate(
        _canary_context(legacy_latency_ms=0.001)
    )

    assert "CANARY_OVERHEAD_TARGET_EXCEEDED" in _codes(result)
    assert result.session.status is RuntimeCanaryStatus.FINISHED
