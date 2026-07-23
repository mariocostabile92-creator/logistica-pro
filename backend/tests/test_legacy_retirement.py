from statistics import median
from time import perf_counter

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.api.dependencies.legacy_retirement import get_legacy_retirement
from app.core.database import db_session
from app.domain.legacy_retirement import (
    LegacyRetirementBlocker,
    LegacyRetirementBlockerSeverity,
    LegacyRetirementContext,
    LegacyRetirementPolicy,
    LegacyRetirementScope,
    LegacyRetirementService,
    LegacyRetirementState,
    LegacyRetirementValidator,
)
from app.domain.runtime_primary import (
    RuntimeCertificationDecision,
    RuntimeCertificationGate,
    RuntimeCertificationGateStatus,
    RuntimeCertificationLevel,
    RuntimeCertificationSnapshot,
    RuntimePrimaryStatus,
)
from app.main import app
from app.runtime.legacy_retirement import LegacyRetirementRuntime
from test_execution_intent import NOW


SCOPE = LegacyRetirementScope(organization_id="organization-a")


class FixedLegacyRetirementProvider:
    def __init__(self, context) -> None:
        self.context = context

    def get(self, *, scope):
        return self.context


def _certification(
    *,
    failed_gate: str | None = None,
    level: RuntimeCertificationLevel = RuntimeCertificationLevel.LEVEL_3,
) -> RuntimeCertificationSnapshot:
    gates = tuple(
        RuntimeCertificationGate(
            code=f"GATE_{index}",
            status=(
                RuntimeCertificationGateStatus.FAIL
                if failed_gate == f"GATE_{index}"
                else RuntimeCertificationGateStatus.PASS
            ),
            evidence_reference=f"evidence://production/gate-{index}",
        )
        for index in range(1, 11)
    )
    return RuntimeCertificationSnapshot(
        level=level,
        decision=(
            RuntimeCertificationDecision.NO_GO
            if failed_gate
            else RuntimeCertificationDecision.GO
        ),
        gates=gates,
        certified_at=NOW,
        record_reference="certification://production/level-3",
    )


def _context(
    *,
    observed_state=LegacyRetirementState.STANDBY,
    runtime_status=RuntimePrimaryStatus.PRIMARY,
    certification=None,
    blockers=(),
    rollback_available=True,
) -> LegacyRetirementContext:
    return LegacyRetirementContext(
        scope=SCOPE,
        observed_state=observed_state,
        runtime_primary_status=runtime_status,
        certification=certification or _certification(),
        open_blockers=blockers,
        critical_mismatch_count=0,
        duplicate_execution_count=0,
        rollback_verified=True,
        rollback_available=rollback_available,
        audit_complete=True,
        canary_complete=True,
        runtime_primary_stable=True,
        runtime_stable_days=30,
        runtime_execution_count=500,
        runtime_success_percent=99.9,
        all_operational_units_enabled=True,
        sev1_incident_count=0,
        sev2_incident_count=0,
        legacy_available=True,
        legacy_observable=True,
        legacy_recoverable=True,
        legacy_code_present=True,
        evaluated_at=NOW,
    )


def _service() -> LegacyRetirementService:
    policy = LegacyRetirementPolicy()
    return LegacyRetirementService(
        validator=LegacyRetirementValidator(policy),
        clock=lambda: NOW,
    )


def _runtime(context) -> LegacyRetirementRuntime:
    return LegacyRetirementRuntime(
        service=_service(),
        provider=FixedLegacyRetirementProvider(context),
    )


def _codes(report):
    return {item.code for item in report.diagnostics.items}


def test_legacy_active_is_observable_without_state_change():
    report = _service().observe(
        _context(observed_state=LegacyRetirementState.ACTIVE)
    )

    assert report.state is LegacyRetirementState.ACTIVE
    assert report.metrics.legacy_active is True
    assert report.metrics.legacy_standby is False
    assert "LEGACY_STANDBY" in _codes(report)


def test_legacy_standby_is_observable_and_recoverable():
    report = _service().observe(_context())

    assert report.state is LegacyRetirementState.STANDBY
    assert report.metrics.legacy_standby is True
    assert report.metrics.legacy_available is True
    assert report.metrics.legacy_observable is True
    assert report.metrics.legacy_recoverable is True


def test_retirement_is_blocked_when_runtime_is_not_primary():
    report = _service().assess(
        _context(runtime_status=RuntimePrimaryStatus.DISABLED)
    )

    assert report.state is LegacyRetirementState.BLOCKED
    assert "RUNTIME_PRIMARY_CERTIFIED" in _codes(report)


def test_complete_level_three_evidence_is_ready_for_retirement():
    report = _service().assess(_context())

    assert report.state is LegacyRetirementState.READY_FOR_RETIREMENT
    assert all(item.passed for item in report.checklist)
    assert report.gates.status is RuntimeCertificationGateStatus.PASS
    assert report.metrics.certification_level is (
        RuntimeCertificationLevel.LEVEL_3
    )
    assert report.reason.endswith("nessuna rimozione eseguita.")


def test_mandatory_gate_failure_blocks_retirement_fail_closed():
    report = _service().assess(
        _context(certification=_certification(failed_gate="GATE_8"))
    )

    assert report.state is LegacyRetirementState.BLOCKED
    assert report.gates.fail_count == 1
    assert report.gates.status is RuntimeCertificationGateStatus.FAIL
    assert "MANDATORY_GATES" in _codes(report)


def test_open_blocker_is_preserved_in_report():
    blocker = LegacyRetirementBlocker(
        code="SECURITY_CERTIFICATION_OPEN",
        severity=LegacyRetirementBlockerSeverity.CRITICAL,
        message="Security certification non completata.",
    )

    report = _service().assess(_context(blockers=(blocker,)))

    assert report.state is LegacyRetirementState.BLOCKED
    assert report.blockers == (blocker,)
    assert "NO_OPEN_BLOCKERS" in _codes(report)


def test_rollback_must_be_verified_and_available():
    report = _service().assess(_context(rollback_available=False))

    assert report.state is LegacyRetirementState.BLOCKED
    assert report.metrics.rollback_available is False
    assert "ROLLBACK_VERIFIED" in _codes(report)


def test_report_is_immutable_and_exposes_complete_sections():
    report = _service().assess(_context())

    assert report.checklist
    assert report.gates.required_count == 10
    assert report.blockers == ()
    assert report.metrics.runtime_readiness is True
    assert report.diagnostics.items
    with pytest.raises(ValidationError):
        report.state = LegacyRetirementState.RETIRED
    with pytest.raises(ValidationError):
        report.metrics.legacy_available = False


def test_default_endpoint_is_blocked_read_only_and_under_payload_target():
    tables = ("plannings", "assignments", "planning_publications")
    with db_session() as conn:
        before = {
            table: conn.execute(
                f"SELECT COUNT(*) AS total FROM {table}"
            ).fetchone()["total"]
            for table in tables
        }

    response = TestClient(app).get(
        "/api/runtime/legacy-retirement",
        params={"organization_id": SCOPE.organization_id},
    )

    with db_session() as conn:
        after = {
            table: conn.execute(
                f"SELECT COUNT(*) AS total FROM {table}"
            ).fetchone()["total"]
            for table in tables
        }
    assert response.status_code == 200
    assert response.json()["report"]["state"] == "BLOCKED"
    assert response.json()["report"]["diagnostics"]["items"][0][
        "code"
    ] == "LEGACY_RETIREMENT_CERTIFICATION_NO_GO"
    assert len(response.content) < 2 * 1024
    assert after == before


def test_endpoint_can_only_assess_a_supplied_context():
    app.dependency_overrides[get_legacy_retirement] = lambda: _runtime(
        _context()
    )
    try:
        response = TestClient(app).get(
            "/api/runtime/legacy-retirement",
            params={"organization_id": SCOPE.organization_id},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["report"]["state"] == "READY_FOR_RETIREMENT"
    assert response.json()["report"]["reason"].endswith(
        "nessuna rimozione eseguita."
    )
    assert len(response.content) < 2 * 1024


def test_openapi_exposes_one_read_only_retirement_operation():
    operation = app.openapi()["paths"][
        "/api/runtime/legacy-retirement"
    ]

    assert set(operation) == {"get"}
    assert not hasattr(_service(), "retire")


def test_retirement_validation_meets_latency_target():
    context = _context()
    service = _service()
    samples = []

    for _ in range(500):
        started = perf_counter()
        report = service.assess(context)
        samples.append((perf_counter() - started) * 1_000)

    assert median(samples) < 10
    assert report.state is LegacyRetirementState.READY_FOR_RETIREMENT
