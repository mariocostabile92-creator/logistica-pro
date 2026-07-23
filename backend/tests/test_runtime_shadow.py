from datetime import timedelta
from statistics import median
from time import perf_counter

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.api.dependencies.runtime_shadow import get_runtime_shadow
from app.domain.runtime_authority import AuthorityResolutionState
from app.domain.runtime_shadow import (
    PlanningComparator,
    PlanningMismatchCategory,
    PlanningMismatchSeverity,
    RuntimeShadowPublication,
    RuntimeShadowScope,
    RuntimeShadowService,
    RuntimeShadowSnapshot,
    RuntimeShadowSource,
    RuntimeShadowState,
)
from app.main import app
from app.runtime.shadow import RuntimeShadowRuntime
from test_execution_attempt import _create_attempt, _intent
from test_execution_intent import NOW, _authority


def _snapshot(
    *,
    source: RuntimeShadowSource,
    intent,
    **changes,
) -> RuntimeShadowSnapshot:
    values = {
        "source": source,
        "scope": RuntimeShadowScope(
            organization_id=intent.scope.organization_id,
            operational_unit_id=intent.scope.operational_unit_id,
            planning_date=intent.scope.planning_date,
            timezone=intent.scope.timezone,
        ),
        "publication": RuntimeShadowPublication(
            publication_id=intent.scope.publication_id,
            publication_version=intent.scope.publication_version,
        ),
        "planning_version": 3,
        "resources": ("resource-a", "resource-b"),
        "fleet": ("asset-a", "asset-b"),
        "assignments": (
            "task-a|resource-a|asset-a",
            "task-b|resource-b|asset-b",
        ),
        "capabilities": ("resource-a:license-b", "asset-a:electric"),
        "availability": ("resource-a:available", "asset-a:available"),
        "fingerprint": "f" * 64,
        "input_fingerprint": "d" * 64,
        "configuration_version": "configuration-v3",
        "rules_version": "rules-v2",
        "validation_errors": (),
        "evaluation_at": NOW,
        "generated_at": (
            NOW
            if source is RuntimeShadowSource.LEGACY
            else NOW + timedelta(milliseconds=2)
        ),
    }
    values.update(changes)
    return RuntimeShadowSnapshot(**values)


def _pipeline():
    intent = _intent()
    attempt = _create_attempt(intent=intent).attempt
    return intent, attempt, _authority(scope=intent.scope)


def _service(*, real_timer: bool = False) -> RuntimeShadowService:
    if real_timer:
        comparator = PlanningComparator(clock=lambda: NOW)
    else:
        samples = iter((10.0, 10.001))
        comparator = PlanningComparator(
            clock=lambda: NOW,
            timer=lambda: next(samples),
        )
    return RuntimeShadowService(comparator=comparator, clock=lambda: NOW)


def _compare(*, runtime_changes=None, authority_state=None):
    intent, attempt, authority = _pipeline()
    if authority_state is not None:
        authority = _authority(
            scope=intent.scope,
            state=authority_state,
        )
    legacy = _snapshot(source=RuntimeShadowSource.LEGACY, intent=intent)
    runtime = _snapshot(
        source=RuntimeShadowSource.RUNTIME,
        intent=intent,
        **(runtime_changes or {}),
    )
    return _service().compare(
        legacy=legacy,
        runtime=runtime,
        authority=authority,
        intent=intent,
        attempt=attempt,
    )


def test_shadow_contract_is_immutable_and_exposes_required_taxonomies():
    result = _compare()

    assert {category.value for category in PlanningMismatchCategory} == {
        "RESOURCE",
        "FLEET",
        "CAPABILITY",
        "ASSIGNMENT",
        "VERSION",
        "FINGERPRINT",
        "SCOPE",
        "VALIDATION",
        "UNKNOWN",
    }
    assert {severity.value for severity in PlanningMismatchSeverity} == {
        "INFO",
        "LOW",
        "MEDIUM",
        "HIGH",
        "CRITICAL",
    }
    with pytest.raises(ValidationError):
        result.state = RuntimeShadowState.REJECTED


def test_perfect_match_reports_full_parity_without_operational_effects():
    result = _compare()

    assert result.state is RuntimeShadowState.COMPLETED
    assert result.report.parity_percent == 100
    assert result.report.mismatch_percent == 0
    assert result.report.perfect_match is True
    assert result.report.parity_target_met is True
    assert result.report.total_mismatches == 0
    assert result.metrics.critical_mismatch == 0
    assert result.metrics.high_mismatch == 0
    assert result.metrics.execution_simulated is True
    assert result.metrics.duplicate_execution == 0
    assert result.metrics.shadow_latency_ms == 2


@pytest.mark.parametrize(
    ("field", "value", "category", "severity"),
    [
        (
            "resources",
            ("resource-a", "resource-c"),
            PlanningMismatchCategory.RESOURCE,
            PlanningMismatchSeverity.HIGH,
        ),
        (
            "fleet",
            ("asset-a", "asset-c"),
            PlanningMismatchCategory.FLEET,
            PlanningMismatchSeverity.HIGH,
        ),
        (
            "capabilities",
            ("resource-a:license-c",),
            PlanningMismatchCategory.CAPABILITY,
            PlanningMismatchSeverity.MEDIUM,
        ),
        (
            "assignments",
            ("task-a|resource-b|asset-a",),
            PlanningMismatchCategory.ASSIGNMENT,
            PlanningMismatchSeverity.CRITICAL,
        ),
        (
            "planning_version",
            4,
            PlanningMismatchCategory.VERSION,
            PlanningMismatchSeverity.HIGH,
        ),
        (
            "fingerprint",
            "e" * 64,
            PlanningMismatchCategory.FINGERPRINT,
            PlanningMismatchSeverity.CRITICAL,
        ),
    ],
)
def test_comparator_classifies_required_mismatches(
    field,
    value,
    category,
    severity,
):
    result = _compare(runtime_changes={field: value})

    assert result.report.perfect_match is False
    assert result.report.parity_percent < 100
    assert any(
        mismatch.category is category and mismatch.severity is severity
        for mismatch in result.mismatches
    )
    mismatch = next(item for item in result.mismatches if item.category is category)
    assert mismatch.id.startswith("mismatch-")
    assert mismatch.title
    assert mismatch.description
    assert mismatch.legacy_value
    assert mismatch.runtime_value
    assert mismatch.difference
    assert mismatch.scope.operational_unit_id == "unit-a"
    assert mismatch.publication.publication_id == "publication-a"
    assert mismatch.suggested_action


def test_scope_mismatch_is_critical_and_explicit():
    changed_scope = RuntimeShadowScope(
        organization_id="organization-a",
        operational_unit_id="unit-b",
        planning_date=NOW.date(),
        timezone="Europe/Rome",
    )
    result = _compare(runtime_changes={"scope": changed_scope})

    mismatch = next(
        item
        for item in result.mismatches
        if item.title == "Operational Unit"
    )
    assert mismatch.category is PlanningMismatchCategory.SCOPE
    assert mismatch.severity is PlanningMismatchSeverity.CRITICAL
    assert result.report.comparable is False
    assert result.report.parity_percent == 0


def test_collection_comparison_counts_missing_and_unexpected_values():
    result = _compare(
        runtime_changes={"resources": ("resource-a", "resource-c")}
    )

    assert result.report.total_mismatches == 1
    assert result.report.missing == 1
    assert result.report.unexpected == 1
    assert "resource-b" in result.mismatches[0].difference
    assert "resource-c" in result.mismatches[0].difference


def test_collection_comparison_detects_duplicate_runtime_values():
    result = _compare(
        runtime_changes={
            "resources": ("resource-a", "resource-b", "resource-b"),
        }
    )

    assert result.report.total_mismatches == 1
    assert result.report.missing == 0
    assert result.report.unexpected == 1
    assert "resource-b" in result.mismatches[0].difference


def test_non_comparable_inputs_fail_parity_closed():
    result = _compare(runtime_changes={"input_fingerprint": "a" * 64})

    assert result.report.comparable is False
    assert result.report.parity_percent == 0
    assert result.report.mismatch_percent == 100
    assert result.report.parity_target_met is False
    assert result.metrics.critical_mismatch == 1


def test_mismatch_ids_and_distribution_are_deterministic():
    changes = {
        "resources": ("resource-a",),
        "fleet": ("asset-a",),
    }
    intent, _, _ = _pipeline()
    legacy = _snapshot(source=RuntimeShadowSource.LEGACY, intent=intent)
    runtime = _snapshot(
        source=RuntimeShadowSource.RUNTIME,
        intent=intent,
        **changes,
    )
    first = PlanningComparator(clock=lambda: NOW).compare(
        legacy=legacy,
        runtime=runtime,
    )
    second = PlanningComparator(clock=lambda: NOW).compare(
        legacy=legacy,
        runtime=runtime,
    )

    assert [item.id for item in first.mismatches] == [
        item.id for item in second.mismatches
    ]
    assert {
        item.category: item.count
        for item in first.report.mismatch_distribution
    } == {
        PlanningMismatchCategory.FLEET: 1,
        PlanningMismatchCategory.RESOURCE: 1,
    }


def test_invalid_authority_rejects_shadow_before_comparison():
    result = _compare(authority_state=AuthorityResolutionState.NO_WRITE)

    assert result.state is RuntimeShadowState.REJECTED
    assert result.report is None
    assert result.metrics is None
    assert result.mismatches == ()
    assert result.diagnostics.items[0].code == "AUTHORITY_INVALID"


class FixedResultProvider:
    def __init__(self, result):
        self.result = result

    def get(self, *, scope, publication_version):
        return self.result


def _runtime(result) -> RuntimeShadowRuntime:
    return RuntimeShadowRuntime(
        service=_service(),
        result_provider=FixedResultProvider(result),
        clock=lambda: NOW,
    )


def _endpoint_params():
    return {
        "organization_id": "organization-a",
        "operational_unit_id": "unit-a",
        "planning_date": NOW.date().isoformat(),
        "timezone": "Europe/Rome",
        "publication_version": 1,
    }


def test_read_only_endpoint_returns_compact_parity_report():
    app.dependency_overrides[get_runtime_shadow] = lambda: _runtime(_compare())
    try:
        response = TestClient(app).get(
            "/api/runtime/shadow",
            params=_endpoint_params(),
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["state"] == "COMPLETED"
    assert response.json()["report"]["parity_percent"] == 100
    assert response.json()["metrics"]["execution_simulated"] is True
    assert len(response.content) < 5 * 1024


def test_endpoint_reports_not_available_without_inventing_output():
    response = TestClient(app).get(
        "/api/runtime/shadow",
        params=_endpoint_params(),
    )

    assert response.status_code == 200
    assert response.json()["state"] == "NOT_AVAILABLE"
    assert response.json()["report"] is None
    assert response.json()["mismatches"] == []
    assert response.json()["diagnostics"]["items"][0]["code"] == (
        "SHADOW_RESULT_NOT_AVAILABLE"
    )


def test_endpoint_rejects_invalid_timezone_without_stack_trace():
    params = _endpoint_params()
    params["timezone"] = "invalid/timezone"

    response = TestClient(app).get("/api/runtime/shadow", params=params)

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == (
        "INVALID_RUNTIME_SHADOW_SCOPE"
    )
    assert "traceback" not in response.text.lower()


def test_openapi_exposes_exactly_one_read_only_shadow_operation():
    operation = app.openapi()["paths"]["/api/runtime/shadow"]

    assert set(operation) == {"get"}


def test_comparator_meets_warm_latency_target():
    intent, _, _ = _pipeline()
    legacy = _snapshot(source=RuntimeShadowSource.LEGACY, intent=intent)
    runtime = _snapshot(source=RuntimeShadowSource.RUNTIME, intent=intent)
    comparator = PlanningComparator(clock=lambda: NOW)
    samples = []

    for _ in range(200):
        started = perf_counter()
        result = comparator.compare(legacy=legacy, runtime=runtime)
        samples.append(perf_counter() - started)
        assert result.report.perfect_match is True

    assert median(samples) < 0.050
