import ast
from datetime import UTC, date, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.domain.core_language import OperationalUnit
from app.domain.planning_conflicts import (
    PlanningConflictCategory,
    PlanningConflictEngine,
    PlanningConflictEvaluator,
    PlanningConflictFormatter,
    PlanningConflictSeverity,
)
from app.domain.planning_readiness import (
    PlanningReadinessBlocker,
    PlanningReadinessDiagnostic,
    PlanningReadinessResult,
    PlanningReadinessScore,
    PlanningReadinessSeverity,
    PlanningReadinessStatus,
    PlanningReadinessWarning,
)
from app.main import app
from app.runtime.planning_conflicts import PlanningConflictService
from app.runtime.planning_readiness import PlanningReadinessEvaluationContext


NOW = datetime(2026, 7, 22, 7, 0, tzinfo=UTC)
OPERATION_DATE = date(2026, 7, 22)
UNIT = OperationalUnit(external_identifier="unit-a", name="Unit A")
APP_DIR = Path(__file__).parents[1] / "app"


def _issue(model, code, *, source="planning-input", category="validation"):
    return model(
        code=code,
        category=category,
        message=f"Diagnostic for {code}.",
        rationale=f"Rationale for {code}.",
        source=source,
        remediation_hint=f"Resolve {code} in {source}.",
    )


def _readiness(
    *,
    blockers=(),
    warnings=(),
    diagnostics=(),
    status=None,
):
    if status is None:
        status = (
            PlanningReadinessStatus.BLOCKED
            if blockers
            else PlanningReadinessStatus.WARNING
            if warnings
            else PlanningReadinessStatus.READY
        )
    ready = status in {
        PlanningReadinessStatus.READY,
        PlanningReadinessStatus.WARNING,
    }
    score_value = 100 if status is PlanningReadinessStatus.READY else 80
    return PlanningReadinessResult(
        status=status,
        score=PlanningReadinessScore(
            value=score_value,
            earned_weight=score_value,
        ),
        is_ready=ready,
        blockers=tuple(blockers),
        warnings=tuple(warnings),
        diagnostics=tuple(diagnostics),
        evaluated_at=NOW,
        operational_unit=UNIT,
        planning_date=OPERATION_DATE,
        envelope_version="input-v1" if ready else None,
        rationale="Synthetic readiness result.",
        legacy_flow_active=True,
    )


def _engine():
    return PlanningConflictEngine(
        PlanningConflictEvaluator(PlanningConflictFormatter())
    )


def _review(readiness):
    return _engine().review(readiness=readiness, envelope=None)


def test_no_conflicts_produces_an_empty_immutable_report():
    result = _review(_readiness())

    assert result.report.total_conflicts == 0
    assert result.report.total_blocking == 0
    assert result.report.total_warnings == 0
    assert result.report.groups == ()
    assert result.report.conflicts == ()
    with pytest.raises(ValidationError):
        result.report.total_conflicts = 1


def test_one_conflict_is_classified_explained_and_actionable():
    readiness = _readiness(
        blockers=(
            _issue(
                PlanningReadinessBlocker,
                "WORKFORCE_PRESENT",
                source="workforce",
                category="completeness",
            ),
        )
    )
    result = _review(readiness)
    conflict = result.report.conflicts[0]

    assert conflict.code == "WORKFORCE_MISSING"
    assert conflict.category is PlanningConflictCategory.WORKFORCE
    assert conflict.severity is PlanningConflictSeverity.CRITICAL
    assert conflict.blocking is True
    assert conflict.suggestion.workspace == "Workforce"
    assert "aggiorna" in conflict.suggestion.action.casefold()
    assert conflict.diagnostics[0].code == "WORKFORCE_PRESENT"


def test_multiple_conflicts_are_grouped_counted_and_sorted_blockers_first():
    readiness = _readiness(
        blockers=(
            _issue(
                PlanningReadinessBlocker,
                "FLEET_AVAILABLE",
                source="fleet",
                category="availability",
            ),
        ),
        warnings=(
            _issue(
                PlanningReadinessWarning,
                "WORKFORCE_CAPABILITIES",
                source="workforce",
                category="capability",
            ),
            _issue(
                PlanningReadinessWarning,
                "FLEET_CAPABILITIES",
                source="fleet",
                category="capability",
            ),
        ),
    )
    result = _review(readiness)
    report = result.report

    assert report.total_conflicts == 3
    assert report.total_blocking == 1
    assert report.total_warnings == 2
    assert report.conflicts[0].code == "ZERO_FLEET_AVAILABLE"
    capability = next(
        group
        for group in report.groups
        if group.category is PlanningConflictCategory.CAPABILITY
    )
    assert capability.total_conflicts == 2
    assert capability.total_blocking == 0


@pytest.mark.parametrize(
    ("raw_code", "source", "category", "expected"),
    (
        ("WORKFORCE_PRESENT", "workforce", "input", "WORKFORCE_MISSING"),
        ("FLEET_PRESENT", "fleet", "input", "FLEET_MISSING"),
        ("OPERATIONAL_UNIT", "runtime-composition", "compatibility", "OPERATIONAL_UNIT_MISMATCH"),
        ("PLANNING_DATE", "runtime-composition", "compatibility", "PLANNING_DATE_MISMATCH"),
        ("DUPLICATE_RESOURCE", "workforce", "validation", "DUPLICATE_RESOURCE"),
        ("WORKFORCE_FRESH", "workforce", "freshness", "WORKFORCE_SNAPSHOT_STALE"),
        ("FLEET_FRESH", "fleet", "freshness", "FLEET_SNAPSHOT_STALE"),
        ("WORKFORCE_CAPABILITIES", "workforce", "capability", "WORKFORCE_CAPABILITIES_MISSING"),
        ("WORKFORCE_AVAILABLE", "workforce", "availability", "ZERO_WORKFORCE_AVAILABLE"),
        ("FLEET_AVAILABLE", "fleet", "availability", "ZERO_FLEET_AVAILABLE"),
        ("VERSION", "runtime-composition", "compatibility", "VERSION_MISMATCH"),
        ("FINGERPRINT", "runtime-composition", "compatibility", "FINGERPRINT_MISMATCH"),
        ("RUNTIME_COMPATIBLE", "runtime-composition", "runtime", "RUNTIME_INCOMPATIBLE"),
        ("ENVELOPE_PRESENT", "runtime-composition", "input", "ENVELOPE_INCOMPLETE"),
        ("DEPENDENCIES_AVAILABLE", "planning-input", "dependency", "DEPENDENCY_MISSING"),
    ),
)
def test_required_conflict_signals_have_stable_core_mappings(
    raw_code,
    source,
    category,
    expected,
):
    issue = _issue(
        PlanningReadinessBlocker,
        raw_code,
        source=source,
        category=category,
    )
    report = _review(_readiness(blockers=(issue,))).report

    assert report.conflicts[0].code == expected


def test_warning_severity_and_stable_identifier_are_deterministic():
    warning = _issue(
        PlanningReadinessWarning,
        "SNAPSHOT_EXPIRING_SOON",
        source="fleet",
        category="freshness",
    )
    readiness = _readiness(warnings=(warning,))
    first = _review(readiness).report.conflicts[0]
    second = _review(readiness).report.conflicts[0]

    assert first.severity is PlanningConflictSeverity.LOW
    assert first.blocking is False
    assert first.id == second.id
    assert {item.value for item in PlanningConflictSeverity} == {
        "INFO",
        "LOW",
        "MEDIUM",
        "HIGH",
        "CRITICAL",
    }


def test_critical_diagnostic_is_blocking_without_duplicate_rule_issue():
    diagnostic = PlanningReadinessDiagnostic(
        code="FINGERPRINT",
        category="compatibility",
        message="Fingerprint mismatch.",
        rationale="Runtime compatibility check.",
        source="runtime-composition",
        severity=PlanningReadinessSeverity.CRITICAL,
        remediation_hint="Regenerate Planning Input.",
    )
    readiness = _readiness(
        diagnostics=(diagnostic,),
        status=PlanningReadinessStatus.INCOMPATIBLE,
    )
    report = _review(readiness).report

    assert report.total_conflicts == 1
    assert report.total_blocking == 1
    assert report.conflicts[0].code == "FINGERPRINT_MISMATCH"


def test_conflict_service_reuses_one_readiness_composition_context():
    class CountingProvider:
        def __init__(self):
            self.calls = 0

        def evaluate_with_context(self, **_):
            self.calls += 1
            return PlanningReadinessEvaluationContext(
                result=_readiness(),
                envelope=None,
            )

    provider = CountingProvider()
    service = PlanningConflictService(
        readiness_provider=provider,
        engine=_engine(),
    )
    result = service.review(
        organization_id="organization-one",
        operational_unit=UNIT,
        operation_date=OPERATION_DATE,
        evaluated_at=NOW,
    )

    assert provider.calls == 1
    assert result.report.total_conflicts == 0


def test_conflict_endpoint_is_compact_and_excludes_source_datasets():
    response = TestClient(app).get(
        "/api/planning/conflicts",
        params={"operation_date": OPERATION_DATE.isoformat()},
    )

    assert response.status_code == 200
    payload = response.json()
    assert set(payload) == {"readiness", "report"}
    assert len(response.content) < 15_000
    assert '"human_resources"' not in response.text
    assert '"registry"' not in response.text
    assert '"snapshots"' not in response.text
    assert "Traceback" not in response.text


def test_conflict_layers_depend_only_on_core_contracts():
    forbidden = (
        "app.plugins",
        "app.repositories",
        "app.importers",
        "app.core.database",
    )
    violations = []
    paths = [
        *(APP_DIR / "domain" / "planning_conflicts").glob("*.py"),
        *(APP_DIR / "runtime" / "planning_conflicts").glob("*.py"),
    ]
    for path in paths:
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
