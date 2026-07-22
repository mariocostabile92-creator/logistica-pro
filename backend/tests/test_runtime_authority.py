from datetime import UTC, date, datetime, timedelta
from statistics import median
from time import perf_counter

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.api.dependencies.runtime_authority import get_authority_runtime
from app.domain.runtime_authority import (
    AuthorityDecision,
    AuthorityDecisionId,
    AuthorityDecisionMode,
    AuthorityDecisionVersion,
    AuthorityFencingTokenError,
    AuthorityResolutionState,
    AuthorityResolver,
    AuthorityScope,
    AuthorityStatus,
    AuthorityValidator,
    AuthorityVersionError,
)
from app.main import app
from app.repositories.authority_repository import AuthorityRepositorySQL
from app.runtime.authority import AuthorityRuntimeService


NOW = datetime(2026, 7, 23, 7, 0, tzinfo=UTC)
SCOPE = AuthorityScope(
    organization_id="organization-a",
    operational_unit_id="unit-a",
    planning_date=date(2026, 7, 23),
    timezone="Europe/Rome",
)


def _decision(
    *,
    decision_id: str = "authority-1",
    scope: AuthorityScope = SCOPE,
    mode: AuthorityDecisionMode = AuthorityDecisionMode.RUNTIME,
    status: AuthorityStatus = AuthorityStatus.ACTIVE,
    priority: int = 10,
    version: int = 1,
    valid_from: datetime | None = None,
    valid_until: datetime | None = None,
    fencing_token: int = 1,
) -> AuthorityDecision:
    return AuthorityDecision(
        decision_id=AuthorityDecisionId(decision_id),
        scope=scope,
        mode=mode,
        status=status,
        priority=priority,
        version=AuthorityDecisionVersion(version),
        valid_from=valid_from or NOW - timedelta(hours=1),
        valid_until=valid_until or NOW + timedelta(hours=1),
        reason="Authority runtime test.",
        actor="test-operator",
        created_at=NOW - timedelta(hours=2),
        fencing_token=fencing_token,
    )


class MemoryAuthorityRepository:
    def __init__(
        self,
        decisions: tuple[AuthorityDecision, ...] = (),
    ) -> None:
        self.decisions = list(decisions)

    def list_for_scope(
        self,
        scope: AuthorityScope,
    ) -> tuple[AuthorityDecision, ...]:
        return tuple(
            decision
            for decision in self.decisions
            if decision.scope.identity == scope.identity
        )

    def get_by_id(
        self,
        decision_id: AuthorityDecisionId,
    ) -> AuthorityDecision | None:
        return next(
            (
                decision
                for decision in self.decisions
                if decision.decision_id == decision_id
            ),
            None,
        )

    def add(self, decision: AuthorityDecision) -> None:
        self.decisions.append(decision)

    def latest_fencing_token(self, scope: AuthorityScope) -> int:
        return max(
            (
                decision.fencing_token
                for decision in self.decisions
                if decision.scope.identity == scope.identity
            ),
            default=0,
        )


def _service(
    decisions: tuple[AuthorityDecision, ...] = (),
) -> AuthorityRuntimeService:
    validator = AuthorityValidator()
    return AuthorityRuntimeService(
        repository=MemoryAuthorityRepository(decisions),
        resolver=AuthorityResolver(validator),
        validator=validator,
        clock=lambda: NOW,
    )


def test_authority_contract_is_typed_immutable_and_timezone_scoped():
    decision = _decision()

    assert decision.scope.identity == (
        "organization-a",
        "unit-a",
        date(2026, 7, 23),
        "Europe/Rome",
    )
    assert {mode.value for mode in AuthorityDecisionMode} == {
        "LEGACY",
        "RUNTIME",
        "SHADOW",
        "VERIFY",
        "ROLLBACK_LOCKED",
        "DISABLED",
    }
    assert {status.value for status in AuthorityStatus} == {
        "ACTIVE",
        "EXPIRED",
        "SUPERSEDED",
        "INVALID",
        "REVOKED",
    }
    with pytest.raises(ValidationError):
        AuthorityScope(
            organization_id="organization-a",
            operational_unit_id="unit-a",
            planning_date=date(2026, 7, 23),
            timezone="not-a-timezone",
        )
    with pytest.raises(ValidationError):
        decision.priority = 100


@pytest.mark.parametrize(
    "mode",
    [AuthorityDecisionMode.LEGACY, AuthorityDecisionMode.RUNTIME],
)
def test_valid_write_authority_returns_write_allowed(mode):
    report = _service((_decision(mode=mode),)).report(SCOPE)

    assert report.resolution.state is AuthorityResolutionState.WRITE_ALLOWED
    assert report.resolution.reason_code == "AUTHORITY_WRITE_ALLOWED"
    assert report.decision is not None
    assert report.decision.mode is mode
    assert report.diagnostics.items[0].message == report.resolution.reason


def test_missing_authority_fails_closed_with_readable_diagnostics():
    report = _service().report(SCOPE)

    assert report.resolution.state is AuthorityResolutionState.NO_WRITE
    assert report.resolution.reason_code == "AUTHORITY_SCOPE_NOT_FOUND"
    assert report.decision is None
    assert report.diagnostics.items[0].message == (
        "Scope non trovato. Nessuna Authority disponibile."
    )


def test_expired_authority_fails_closed():
    report = _service(
        (
            _decision(
                valid_from=NOW - timedelta(hours=2),
                valid_until=NOW - timedelta(seconds=1),
            ),
        )
    ).report(SCOPE)

    assert report.resolution.state is AuthorityResolutionState.NO_WRITE
    assert report.resolution.reason_code == "AUTHORITY_EXPIRED"
    assert report.decision is not None
    assert report.decision.status is AuthorityStatus.EXPIRED
    assert report.diagnostics.items[0].message == (
        "Authority scaduta. Scrittura bloccata."
    )


def test_overlapping_authorities_fail_closed_even_with_priority_and_version():
    report = _service(
        (
            _decision(priority=1, version=1, fencing_token=1),
            _decision(
                decision_id="authority-2",
                priority=100,
                version=2,
                fencing_token=2,
            ),
        )
    ).report(SCOPE)

    assert report.resolution.state is AuthorityResolutionState.NO_WRITE
    assert report.resolution.reason_code == "AUTHORITY_CONFLICT"
    assert report.resolution.decision is None
    assert len(report.resolution.conflicts) == 1
    assert report.resolution.conflicts[0].priorities == (100, 1)
    assert report.diagnostics.items[1].message == (
        "Authority sovrapposta. Nessun writer autorizzato."
    )


@pytest.mark.parametrize(
    "mode",
    [
        AuthorityDecisionMode.SHADOW,
        AuthorityDecisionMode.VERIFY,
        AuthorityDecisionMode.ROLLBACK_LOCKED,
        AuthorityDecisionMode.DISABLED,
    ],
)
def test_non_writer_modes_never_authorize_writes(mode):
    resolution = _service((_decision(mode=mode),)).resolve(SCOPE)

    assert resolution.state is AuthorityResolutionState.NO_WRITE
    assert resolution.reason_code == "AUTHORITY_MODE_NO_WRITE"


def test_stale_fencing_token_is_always_rejected():
    decision = _decision(fencing_token=7)
    service = _service((decision,))

    current = service.validate_writer(
        scope=SCOPE,
        decision_id=decision.decision_id,
        fencing_token=7,
    )
    stale = service.validate_writer(
        scope=SCOPE,
        decision_id=decision.decision_id,
        fencing_token=6,
    )

    assert current.state is AuthorityResolutionState.WRITE_ALLOWED
    assert stale.state is AuthorityResolutionState.NO_WRITE
    assert stale.reason_code == "STALE_FENCING_TOKEN"
    assert stale.reason == "Fencing token obsoleto o non riconosciuto."


def test_sql_repository_persists_versions_and_monotonic_fencing_tokens():
    repository = AuthorityRepositorySQL()
    first = _decision()
    second = _decision(
        decision_id="authority-2",
        version=2,
        fencing_token=2,
    )

    repository.add(first)
    repository.add(second)

    stored = repository.list_for_scope(SCOPE)
    assert [int(item.version) for item in stored] == [2, 1]
    assert repository.get_by_id(first.decision_id) == first
    assert repository.latest_fencing_token(SCOPE) == 2


def test_sql_repository_rejects_version_gaps_and_stale_fencing_tokens():
    repository = AuthorityRepositorySQL()
    repository.add(_decision())

    with pytest.raises(AuthorityVersionError):
        repository.add(
            _decision(
                decision_id="authority-version-gap",
                version=3,
                fencing_token=2,
            )
        )
    with pytest.raises(AuthorityFencingTokenError):
        repository.add(
            _decision(
                decision_id="authority-stale-token",
                version=2,
                fencing_token=1,
            )
        )


def test_read_only_authority_endpoint_returns_compact_report():
    app.dependency_overrides[get_authority_runtime] = lambda: _service(
        (_decision(),)
    )
    try:
        response = TestClient(app).get(
            "/api/runtime/authority",
            params={
                "organization_id": "organization-a",
                "operational_unit_id": "unit-a",
                "planning_date": "2026-07-23",
                "timezone": "Europe/Rome",
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["resolution"]["state"] == "WRITE_ALLOWED"
    assert set(response.json()) == {
        "decision",
        "resolution",
        "diagnostics",
        "generated_at",
    }
    assert len(response.content) < 2 * 1024


def test_authority_endpoint_rejects_invalid_scope_without_stack_trace():
    response = TestClient(app).get(
        "/api/runtime/authority",
        params={
            "organization_id": "organization-a",
            "operational_unit_id": "unit-a",
            "planning_date": "2026-07-23",
            "timezone": "invalid/timezone",
        },
    )

    assert response.status_code == 422
    assert response.json() == {
        "detail": {
            "code": "INVALID_AUTHORITY_SCOPE",
            "message": "Scope Authority non valido.",
        }
    }
    assert "traceback" not in response.text.lower()


def test_openapi_exposes_exactly_one_read_only_authority_operation():
    authority_path = app.openapi()["paths"]["/api/runtime/authority"]

    assert set(authority_path) == {"get"}


def test_resolver_and_repository_meet_warm_latency_targets():
    decision = _decision()
    validator = AuthorityValidator()
    resolver = AuthorityResolver(validator)
    repository = AuthorityRepositorySQL()
    repository.add(decision)

    resolver.resolve(scope=SCOPE, decisions=(decision,), assessed_at=NOW)
    repository.list_for_scope(SCOPE)
    resolver_samples = []
    repository_samples = []
    for _ in range(50):
        started = perf_counter()
        resolver.resolve(scope=SCOPE, decisions=(decision,), assessed_at=NOW)
        resolver_samples.append(perf_counter() - started)

        started = perf_counter()
        repository.list_for_scope(SCOPE)
        repository_samples.append(perf_counter() - started)

    assert median(resolver_samples) < 0.010
    assert median(repository_samples) < 0.020
