from app.domain.runtime_canary.models import (
    RuntimeCanaryCriterion,
    RuntimeCanaryEvaluationContext,
    RuntimeCanaryMetrics,
    RuntimeCanaryPolicy,
)
from app.domain.runtime_shadow import PlanningMismatchSeverity


def calculate_canary_metrics(
    context: RuntimeCanaryEvaluationContext,
) -> RuntimeCanaryMetrics:
    shadow = context.shadow_result
    producer = context.producer_result
    mismatches = shadow.mismatches if shadow is not None else ()
    shadow_metrics = shadow.metrics if shadow is not None else None
    shadow_report = shadow.report if shadow is not None else None
    producer_metrics = producer.metrics if producer is not None else None
    comparator_latency = (
        shadow_report.comparison_time_ms if shadow_report else 0.0
    )
    producer_latency = (
        producer_metrics.producer_latency_ms if producer_metrics else 0.0
    )
    overhead = None
    if context.legacy_latency_ms is not None:
        overhead = round(
            (producer_latency + comparator_latency)
            / context.legacy_latency_ms
            * 100,
            4,
        )
    return RuntimeCanaryMetrics(
        parity_percent=(
            shadow_report.parity_percent if shadow_report else 0.0
        ),
        critical_mismatch=sum(
            item.severity is PlanningMismatchSeverity.CRITICAL
            for item in mismatches
        ),
        high_mismatch=sum(
            item.severity is PlanningMismatchSeverity.HIGH
            for item in mismatches
        ),
        medium_mismatch=sum(
            item.severity is PlanningMismatchSeverity.MEDIUM
            for item in mismatches
        ),
        low_mismatch=sum(
            item.severity is PlanningMismatchSeverity.LOW
            for item in mismatches
        ),
        duplicate_execution=(
            shadow_metrics.duplicate_execution if shadow_metrics else 0
        ),
        authority_conflict=(
            1
            if context.authority.reason_code == "AUTHORITY_CONFLICT"
            or context.authority.conflicts
            else 0
        ),
        shadow_latency_ms=(
            shadow_metrics.shadow_latency_ms if shadow_metrics else 0.0
        ),
        producer_latency_ms=producer_latency,
        comparator_latency_ms=comparator_latency,
        canary_overhead_percent=overhead,
    )


def evaluate_canary_criteria(
    metrics: RuntimeCanaryMetrics,
    *,
    policy: RuntimeCanaryPolicy,
    prerequisites_valid: bool,
) -> tuple[RuntimeCanaryCriterion, ...]:
    return (
        RuntimeCanaryCriterion(
            code="PREREQUISITES",
            passed=prerequisites_valid,
            actual=str(prerequisites_valid).lower(),
            expected="true",
        ),
        RuntimeCanaryCriterion(
            code="PARITY",
            passed=metrics.parity_percent >= policy.minimum_parity_percent,
            actual=f"{metrics.parity_percent:.2f}%",
            expected=f">={policy.minimum_parity_percent:.2f}%",
        ),
        RuntimeCanaryCriterion(
            code="CRITICAL_MISMATCH",
            passed=(
                metrics.critical_mismatch
                <= policy.maximum_critical_mismatch
            ),
            actual=str(metrics.critical_mismatch),
            expected=f"<={policy.maximum_critical_mismatch}",
        ),
        RuntimeCanaryCriterion(
            code="DUPLICATE_EXECUTION",
            passed=(
                metrics.duplicate_execution
                <= policy.maximum_duplicate_execution
            ),
            actual=str(metrics.duplicate_execution),
            expected=f"<={policy.maximum_duplicate_execution}",
        ),
        RuntimeCanaryCriterion(
            code="AUTHORITY_CONFLICT",
            passed=(
                metrics.authority_conflict
                <= policy.maximum_authority_conflict
            ),
            actual=str(metrics.authority_conflict),
            expected=f"<={policy.maximum_authority_conflict}",
        ),
    )
