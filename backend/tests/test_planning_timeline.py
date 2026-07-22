import ast
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.domain.core_language import (
    AssetReference,
    HumanResource,
    OperationalUnit,
    ResourceAvailability,
    ResourceKind,
    TimeWindow,
)
from app.domain.planning_conflicts import (
    PlanningConflictEngine,
    PlanningConflictEvaluator,
    PlanningConflictFormatter,
)
from app.domain.planning_inputs import (
    FleetPlanningInput,
    PlanningAssetRegistry,
    PlanningCoverage,
    PlanningInputScope,
    PlanningInputType,
    PlanningResourceCapability,
    WorkforcePlanningInput,
    build_planning_input_snapshot,
)
from app.domain.planning_readiness import (
    PlanningReadinessResult,
    PlanningReadinessScore,
    PlanningReadinessStatus,
    PlanningReadinessWarning,
)
from app.domain.planning_timeline import (
    PlanningTimelineCategory,
    PlanningTimelineEngine,
    PlanningTimelineFormatter,
    PlanningTimelineReport,
    PlanningTimelineResult,
    PlanningTimelineSeverity,
)
from app.domain.planning_timeline.grouping import (
    group_planning_timeline_events,
    sort_planning_timeline_events,
)
from app.main import app
from app.runtime.planning_conflicts import PlanningConflictReviewContext
from app.runtime.planning_inputs import (
    PlanningInputCompatibility,
    PlanningInputCompatibilityCheck,
    PlanningInputCompositionReport,
    PlanningInputDiagnostics,
    PlanningInputRuntimeStatus,
)
from app.runtime.planning_timeline import PlanningTimelineRuntimeService


NOW = datetime(2026, 7, 22, 10, 0, tzinfo=UTC)
OPERATION_DATE = date(2026, 7, 22)
UNIT = OperationalUnit(external_identifier="unit-a", name="Unit A")
APP_DIR = Path(__file__).parents[1] / "app"


def _snapshots():
    scope = PlanningInputScope(
        organization_id="organization-one",
        operational_unit=UNIT,
        operation_date=OPERATION_DATE,
    )
    observed_at = NOW - timedelta(minutes=20)
    workforce = build_planning_input_snapshot(
        input_type=PlanningInputType.WORKFORCE,
        producer="workforce",
        contract_name="WorkforcePlanningInput",
        scope=scope,
        payload=WorkforcePlanningInput(
            human_resources=(
                HumanResource(
                    external_identifier="human-001",
                    display_name="Resource 1",
                ),
            ),
            availability=(
                ResourceAvailability(
                    resource_identifier="human-001",
                    resource_kind=ResourceKind.HUMAN_RESOURCE,
                    available=True,
                ),
            ),
            capabilities=(
                PlanningResourceCapability(
                    resource_identifier="human-001",
                    resource_kind=ResourceKind.HUMAN_RESOURCE,
                    capability="license-b",
                ),
            ),
            coverage=PlanningCoverage(
                required=1,
                available=1,
                scheduled=1,
                unavailable=0,
                margin=0,
                status="covered",
            ),
            time_windows=(
                TimeWindow(
                    external_identifier="morning",
                    starts_at="07:00",
                    ends_at="15:00",
                ),
            ),
        ),
        observed_at=observed_at,
        assessed_at=observed_at,
        freshness_ttl=timedelta(hours=1),
    )
    fleet = build_planning_input_snapshot(
        input_type=PlanningInputType.FLEET,
        producer="fleet",
        contract_name="FleetPlanningInput",
        scope=scope,
        payload=FleetPlanningInput(
            registry=PlanningAssetRegistry(
                assets=(
                    AssetReference(
                        external_identifier="asset-001",
                        category="van",
                    ),
                ),
            ),
            availability=(
                ResourceAvailability(
                    resource_identifier="asset-001",
                    resource_kind=ResourceKind.ASSET,
                    available=True,
                ),
            ),
            capabilities=(
                PlanningResourceCapability(
                    resource_identifier="asset-001",
                    resource_kind=ResourceKind.ASSET,
                    capability="electric",
                ),
            ),
        ),
        observed_at=observed_at,
        assessed_at=observed_at,
        freshness_ttl=timedelta(hours=1),
    )
    return workforce, fleet


def _composition():
    workforce, fleet = _snapshots()
    return PlanningInputCompositionReport(
        workforce=workforce,
        fleet=fleet,
        status=PlanningInputRuntimeStatus.READY,
        compatibility=PlanningInputCompatibility(
            compatible=True,
            checks=(
                PlanningInputCompatibilityCheck(
                    code="INPUTS_READY",
                    compatible=True,
                    message="Inputs are compatible.",
                ),
            ),
        ),
        diagnostics=PlanningInputDiagnostics(),
        timestamp=NOW - timedelta(minutes=5),
        legacy_flow_active=True,
    )


def _readiness(*, warning=False, legacy=True):
    warnings = ()
    status = PlanningReadinessStatus.READY
    if warning:
        status = PlanningReadinessStatus.WARNING
        warnings = (
            PlanningReadinessWarning(
                code="WORKFORCE_CAPABILITIES",
                category="capability",
                message="Workforce capabilities require verification.",
                rationale="Synthetic warning.",
                source="workforce",
                remediation_hint="Complete Workforce capabilities.",
            ),
        )
    score = 95 if warning else 100
    return PlanningReadinessResult(
        status=status,
        score=PlanningReadinessScore(value=score, earned_weight=score),
        is_ready=True,
        warnings=warnings,
        evaluated_at=NOW - timedelta(minutes=4),
        operational_unit=UNIT,
        planning_date=OPERATION_DATE,
        envelope_version="input-v1",
        envelope_fingerprint="input-v1",
        rationale="Synthetic readiness completed.",
        legacy_flow_active=legacy,
    )


def _conflicts(readiness):
    engine = PlanningConflictEngine(
        PlanningConflictEvaluator(PlanningConflictFormatter())
    )
    return engine.review(readiness=readiness, envelope=None)


def _timeline(*, warning=True, legacy=True):
    readiness = _readiness(warning=warning, legacy=legacy)
    conflicts = _conflicts(readiness).report
    return PlanningTimelineEngine(PlanningTimelineFormatter()).build(
        readiness=readiness,
        conflicts=conflicts,
        composition=_composition(),
        evaluated_at=NOW,
    )


def test_empty_timeline_report_is_valid_and_immutable():
    report = PlanningTimelineReport(
        event_count=0,
        last_updated=None,
        current_status="MISSING",
        groups=(),
        events=(),
    )

    assert report.events == ()
    with pytest.raises(ValidationError):
        report.event_count = 1


def test_complete_timeline_contains_the_required_observed_events():
    result = _timeline()
    categories = {event.category for event in result.report.events}

    assert {
        PlanningTimelineCategory.IMPORT,
        PlanningTimelineCategory.RUNTIME,
        PlanningTimelineCategory.READINESS,
        PlanningTimelineCategory.CONFLICT,
        PlanningTimelineCategory.WORKFORCE,
        PlanningTimelineCategory.FLEET,
        PlanningTimelineCategory.LEGACY,
    } <= categories
    assert result.report.event_count == 7


def test_events_are_sorted_newest_first_with_stable_identifiers():
    first = _timeline().report
    second = _timeline().report
    timestamps = [event.timestamp for event in first.events]

    assert timestamps == sorted(timestamps, reverse=True)
    assert [event.id for event in first.events] == [
        event.id for event in second.events
    ]
    assert first.last_updated == first.events[0].timestamp


def test_events_are_grouped_exclusively_by_last_hour_today_and_older():
    formatter = PlanningTimelineFormatter()
    events = tuple(
        formatter.format(
            timestamp=timestamp,
            category=PlanningTimelineCategory.SYSTEM,
            severity=PlanningTimelineSeverity.INFO,
            title=label,
            description=f"Synthetic {label} event.",
            status="OBSERVED",
            source="test",
            operational_unit=UNIT,
            planning_date=OPERATION_DATE,
            reference=label,
        )
        for label, timestamp in (
            ("recent", NOW - timedelta(minutes=10)),
            ("today", NOW - timedelta(hours=2)),
            ("older", NOW - timedelta(days=1)),
        )
    )
    ordered = sort_planning_timeline_events(events)
    groups = group_planning_timeline_events(ordered, evaluated_at=NOW)

    assert [group.key for group in groups] == [
        "LAST_HOUR",
        "TODAY",
        "OLDER",
    ]
    assert [group.event_count for group in groups] == [1, 1, 1]
    assert len({event_id for group in groups for event_id in group.event_ids}) == 3


def test_categories_and_severities_are_complete():
    assert {item.value for item in PlanningTimelineCategory} == {
        "IMPORT",
        "VALIDATION",
        "WORKFORCE",
        "FLEET",
        "READINESS",
        "CONFLICT",
        "RUNTIME",
        "SYSTEM",
        "LEGACY",
    }
    assert {item.value for item in PlanningTimelineSeverity} == {
        "INFO",
        "SUCCESS",
        "WARNING",
        "ERROR",
        "CRITICAL",
    }


def test_absent_conflicts_do_not_invent_a_resolved_event():
    report = _timeline(warning=False, legacy=False).report

    assert all(
        event.category is not PlanningTimelineCategory.CONFLICT
        for event in report.events
    )
    assert all("risol" not in event.title.casefold() for event in report.events)


def test_runtime_service_consumes_one_cached_review_context():
    readiness = _readiness()
    conflicts = _conflicts(readiness)

    class ReviewProvider:
        def __init__(self):
            self.calls = 0

        def review_with_context(self, **_):
            self.calls += 1
            return PlanningConflictReviewContext(
                result=conflicts,
                readiness=readiness,
                composition_report=_composition(),
                evaluated_at=NOW,
            )

    provider = ReviewProvider()
    service = PlanningTimelineRuntimeService(
        review_provider=provider,
        engine=PlanningTimelineEngine(PlanningTimelineFormatter()),
    )
    result = service.timeline(
        organization_id="organization-one",
        operational_unit=UNIT,
        operation_date=OPERATION_DATE,
        evaluated_at=NOW,
    )

    assert provider.calls == 1
    assert isinstance(result, PlanningTimelineResult)


def test_timeline_endpoint_is_compact_bounded_and_excludes_source_datasets():
    client = TestClient(app)
    params = {"operation_date": OPERATION_DATE.isoformat()}
    client.get("/api/planning/conflicts", params=params)
    response = client.get("/api/planning/timeline", params=params)

    assert response.status_code == 200
    payload = response.json()
    assert set(payload) == {"report"}
    assert payload["report"]["event_count"] <= 100
    assert len(response.content) < 10_000
    assert '"human_resources"' not in response.text
    assert '"registry"' not in response.text
    assert '"snapshots"' not in response.text
    assert "Traceback" not in response.text


def test_timeline_openapi_exposes_one_read_only_typed_operation():
    operation = app.openapi()["paths"]["/api/planning/timeline"]
    response_schema = operation["get"]["responses"]["200"]["content"][
        "application/json"
    ]["schema"]

    assert set(operation) == {"get"}
    assert response_schema["$ref"] == "#/components/schemas/PlanningTimelineResult"


def test_timeline_domain_has_no_outer_layer_dependencies():
    forbidden = (
        "app.runtime",
        "app.plugins",
        "app.repositories",
        "app.importers",
        "app.core.database",
    )
    violations = []
    for path in (APP_DIR / "domain" / "planning_timeline").glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            modules = []
            if isinstance(node, ast.ImportFrom) and node.module:
                modules.append(node.module)
            elif isinstance(node, ast.Import):
                modules.extend(alias.name for alias in node.names)
            violations.extend(
                f"{path.name}: {module}"
                for module in modules
                if module.startswith(forbidden)
            )

    assert violations == []
