from datetime import UTC, date, datetime, timedelta
from statistics import median
from time import perf_counter

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.api.dependencies.execution_intent import (
    get_execution_intent_runtime,
)
from app.core.database import db_session
from app.domain.execution_intent import (
    ExecutionIntent,
    ExecutionIntentCommand,
    ExecutionIntentId,
    ExecutionIntentKey,
    ExecutionIntentMode,
    ExecutionIntentRepositoryConflictError,
    ExecutionIntentScope,
    ExecutionIntentService,
    ExecutionIntentStatus,
    ExecutionIntentValidator,
    ExecutionIntentVersion,
    ExecutionIntentVersionError,
    ExecutionPublicationReference,
    ExecutionPublicationStatus,
    execution_intent_key,
)
from app.domain.runtime_authority import (
    AuthorityDecision,
    AuthorityDecisionId,
    AuthorityDecisionMode,
    AuthorityDecisionVersion,
    AuthorityResolutionResult,
    AuthorityResolutionState,
    AuthorityScope,
)
from app.main import app
from app.repositories.execution_intent_repository import (
    ExecutionIntentRepositorySQL,
)
from app.runtime.execution_intent import ExecutionIntentRuntime


NOW = datetime(2026, 7, 23, 7, 0, tzinfo=UTC)
SCOPE = ExecutionIntentScope(
    organization_id="organization-a",
    operational_unit_id="unit-a",
    planning_date=date(2026, 7, 23),
    timezone="Europe/Rome",
    publication_id="publication-a",
    publication_version=1,
    execution_mode=ExecutionIntentMode.NORMAL,
)
PUBLICATION_FINGERPRINT = "a" * 64


def _authority_scope(scope: ExecutionIntentScope = SCOPE) -> AuthorityScope:
    return AuthorityScope(
        organization_id=scope.organization_id,
        operational_unit_id=scope.operational_unit_id,
        planning_date=scope.planning_date,
        timezone=scope.timezone,
    )


def _authority(
    *,
    scope: ExecutionIntentScope = SCOPE,
    state: AuthorityResolutionState = AuthorityResolutionState.WRITE_ALLOWED,
    fencing_token: int = 7,
) -> AuthorityResolutionResult:
    authority_scope = _authority_scope(scope)
    decision = None
    if state is AuthorityResolutionState.WRITE_ALLOWED:
        decision = AuthorityDecision(
            decision_id=AuthorityDecisionId("authority-a"),
            scope=authority_scope,
            mode=AuthorityDecisionMode.RUNTIME,
            priority=10,
            version=AuthorityDecisionVersion(1),
            valid_from=NOW - timedelta(hours=1),
            valid_until=NOW + timedelta(hours=1),
            reason="Execution Intent test authority.",
            actor="authority-operator",
            created_at=NOW - timedelta(hours=2),
            fencing_token=fencing_token,
        )
    return AuthorityResolutionResult(
        state=state,
        scope=authority_scope,
        decision=decision,
        reason_code=(
            "AUTHORITY_WRITE_ALLOWED"
            if state is AuthorityResolutionState.WRITE_ALLOWED
            else "AUTHORITY_SCOPE_NOT_FOUND"
        ),
        reason=(
            "Authority valida."
            if state is AuthorityResolutionState.WRITE_ALLOWED
            else "Authority non valida."
        ),
        assessed_at=NOW,
    )


def _publication(
    *,
    scope: ExecutionIntentScope = SCOPE,
    status: ExecutionPublicationStatus = ExecutionPublicationStatus.PUBLISHED,
    publication_version: int | None = None,
) -> ExecutionPublicationReference:
    return ExecutionPublicationReference(
        organization_id=scope.organization_id,
        operational_unit_id=scope.operational_unit_id,
        planning_date=scope.planning_date,
        publication_id=scope.publication_id,
        publication_version=(
            publication_version
            if publication_version is not None
            else scope.publication_version
        ),
        fingerprint=PUBLICATION_FINGERPRINT,
        status=status,
    )


def _command(
    *,
    scope: ExecutionIntentScope = SCOPE,
    idempotency_key: str = "intent-command-0001",
    expected_version: int = 0,
    fencing_token: int = 7,
    publication_fingerprint: str = PUBLICATION_FINGERPRINT,
) -> ExecutionIntentCommand:
    return ExecutionIntentCommand(
        scope=scope,
        publication_fingerprint=publication_fingerprint,
        idempotency_key=idempotency_key,
        expected_version=expected_version,
        authority_decision_id=AuthorityDecisionId("authority-a"),
        fencing_token=fencing_token,
        actor="execution-operator",
    )


class MemoryExecutionIntentRepository:
    def __init__(self) -> None:
        self.intents: list[ExecutionIntent] = []

    def get_by_key(
        self,
        intent_key: ExecutionIntentKey,
    ) -> ExecutionIntent | None:
        matching = [
            item for item in self.intents if item.intent_key == intent_key
        ]
        return max(matching, key=lambda item: int(item.version), default=None)

    def get_by_idempotency_key(
        self,
        *,
        organization_id: str,
        idempotency_key: str,
    ) -> ExecutionIntent | None:
        return next(
            (
                item
                for item in reversed(self.intents)
                if item.scope.organization_id == organization_id
                and item.idempotency_key == idempotency_key
            ),
            None,
        )

    def list_for_scope(
        self,
        scope: ExecutionIntentScope,
    ) -> tuple[ExecutionIntent, ...]:
        return tuple(
            item for item in self.intents if item.scope.identity == scope.identity
        )

    def append(self, intent: ExecutionIntent) -> None:
        if self.get_by_key(intent.intent_key) is not None:
            raise ExecutionIntentRepositoryConflictError("Duplicate intent.")
        self.intents.append(intent)


class Identifiers:
    def __init__(self) -> None:
        self.value = 0

    def __call__(self) -> str:
        self.value += 1
        return f"{self.value:032d}"


def _service(repository=None) -> ExecutionIntentService:
    return ExecutionIntentService(
        repository=repository or ExecutionIntentRepositorySQL(),
        validator=ExecutionIntentValidator(),
        clock=lambda: NOW,
        identifier_factory=Identifiers(),
    )


def _create(service=None, **command_changes):
    selected = service or _service()
    return selected.create(
        command=_command(**command_changes),
        publication=_publication(
            scope=command_changes.get("scope", SCOPE)
        ),
        authority=_authority(
            scope=command_changes.get("scope", SCOPE),
            fencing_token=7,
        ),
    )


def test_execution_intent_contract_is_immutable_and_has_no_attempt_states():
    result = _create()

    assert {status.value for status in ExecutionIntentStatus} == {
        "CREATED",
        "READY",
        "LOCKED",
        "CANCELLED",
        "SUPERSEDED",
        "REJECTED",
    }
    assert {mode.value for mode in ExecutionIntentMode} == {
        "NORMAL",
        "SHADOW",
        "VERIFY",
        "ROLLBACK",
    }
    assert not {"RUNNING", "SUCCESS", "FAILED"}.intersection(
        status.value for status in ExecutionIntentStatus
    )
    with pytest.raises(ValidationError):
        result.intent.status = ExecutionIntentStatus.LOCKED


def test_intent_key_is_deterministic_and_scoped_by_publication_and_mode():
    first = execution_intent_key(SCOPE)
    same = execution_intent_key(SCOPE.model_copy())
    other_mode = execution_intent_key(
        SCOPE.model_copy(update={"execution_mode": ExecutionIntentMode.VERIFY})
    )
    other_version = execution_intent_key(
        SCOPE.model_copy(update={"publication_version": 2})
    )

    assert first == same
    assert len(str(first)) == 64
    assert first != other_mode
    assert first != other_version


def test_write_allowed_authority_creates_ready_intent_without_execution():
    result = _create()

    assert result.status is ExecutionIntentStatus.READY
    assert result.intent is not None
    assert result.intent.status is ExecutionIntentStatus.READY
    assert result.intent.attempt_reference is None
    assert result.validation.allowed is True
    assert result.idempotent is False


def test_no_write_authority_rejects_without_persisting_intent():
    repository = ExecutionIntentRepositorySQL()
    result = _service(repository).create(
        command=_command(),
        publication=_publication(),
        authority=_authority(state=AuthorityResolutionState.NO_WRITE),
    )

    assert result.status is ExecutionIntentStatus.REJECTED
    assert result.intent is None
    assert repository.list_for_scope(SCOPE) == ()
    assert "Authority non valida." in {
        item.message for item in result.diagnostics.items
    }


def test_duplicate_intent_with_different_command_is_rejected():
    service = _service()
    first = _create(service)
    duplicate = _create(
        service,
        idempotency_key="intent-command-0002",
    )

    assert first.status is ExecutionIntentStatus.READY
    assert duplicate.status is ExecutionIntentStatus.REJECTED
    assert duplicate.intent is None
    assert duplicate.validation.rules[-1].code == "EXECUTION_INTENT_UNIQUE"


def test_same_idempotency_command_returns_exact_same_intent():
    service = _service()
    first = _create(service)
    replay = _create(service)

    assert replay.status is ExecutionIntentStatus.READY
    assert replay.idempotent is True
    assert replay.intent == first.intent
    assert len(ExecutionIntentRepositorySQL().list_for_scope(SCOPE)) == 1


def test_idempotency_key_reuse_with_different_payload_is_rejected():
    service = _service()
    _create(service)
    conflict = _create(
        service,
        publication_fingerprint="b" * 64,
    )

    assert conflict.status is ExecutionIntentStatus.REJECTED
    assert conflict.diagnostics.items[0].code == "IDEMPOTENCY_KEY_CONFLICT"


@pytest.mark.parametrize(
    ("status", "message"),
    [
        (ExecutionPublicationStatus.SUPERSEDED, "Publication superseded."),
        (ExecutionPublicationStatus.REVOKED, "Publication revoked."),
    ],
)
def test_inactive_publication_is_rejected(status, message):
    result = _service().create(
        command=_command(),
        publication=_publication(status=status),
        authority=_authority(),
    )

    assert result.status is ExecutionIntentStatus.REJECTED
    assert message in {item.message for item in result.diagnostics.items}


def test_publication_version_mismatch_is_rejected():
    scope = SCOPE.model_copy(update={"publication_version": 2})
    result = _service().create(
        command=_command(scope=scope),
        publication=_publication(scope=scope, publication_version=1),
        authority=_authority(scope=scope),
    )

    assert result.status is ExecutionIntentStatus.REJECTED
    assert "Version mismatch." in {
        item.message for item in result.diagnostics.items
    }


def test_fencing_mismatch_is_rejected():
    result = _service().create(
        command=_command(fencing_token=6),
        publication=_publication(),
        authority=_authority(fencing_token=7),
    )

    assert result.status is ExecutionIntentStatus.REJECTED
    assert "Fencing token obsoleto." in {
        item.message for item in result.diagnostics.items
    }


def test_expected_version_mismatch_is_rejected():
    result = _create(expected_version=1)

    assert result.status is ExecutionIntentStatus.REJECTED
    assert "Version mismatch." in {
        item.message for item in result.diagnostics.items
    }


def test_sql_repository_is_append_only_and_returns_latest_version():
    repository = ExecutionIntentRepositorySQL()
    first = _create(_service(repository)).intent
    cancelled = first.model_copy(
        update={
            "version": ExecutionIntentVersion(2),
            "status": ExecutionIntentStatus.CANCELLED,
            "idempotency_key": "intent-transition-0002",
        }
    )

    repository.append(cancelled)

    assert repository.get_by_key(first.intent_key) == cancelled
    assert [int(item.version) for item in repository.list_for_scope(SCOPE)] == [2, 1]
    with db_session() as conn:
        rows = conn.execute(
            """
            SELECT version, status
            FROM runtime_execution_intents
            WHERE intent_key = ?
            ORDER BY version
            """,
            (str(first.intent_key),),
        ).fetchall()
    assert [(row["version"], row["status"]) for row in rows] == [
        (1, "READY"),
        (2, "CANCELLED"),
    ]


def test_sql_repository_rejects_version_gaps_and_duplicate_ids():
    repository = ExecutionIntentRepositorySQL()
    first = _create(_service(repository)).intent

    with pytest.raises(ExecutionIntentVersionError):
        repository.append(
            first.model_copy(
                update={
                    "version": ExecutionIntentVersion(3),
                    "status": ExecutionIntentStatus.CANCELLED,
                    "idempotency_key": "intent-version-gap",
                }
            )
        )
    with pytest.raises(ExecutionIntentRepositoryConflictError):
        repository.append(
            first.model_copy(
                update={
                    "intent_id": ExecutionIntentId("different-intent"),
                    "version": ExecutionIntentVersion(2),
                    "status": ExecutionIntentStatus.CANCELLED,
                    "idempotency_key": "intent-different-id",
                }
            )
        )


class FixedPublicationProvider:
    def get(self, scope):
        return _publication(scope=scope)


class FixedAuthorityProvider:
    def validate_writer(self, *, scope, decision_id, fencing_token):
        execution_scope = SCOPE.model_copy(
            update={
                "organization_id": scope.organization_id,
                "operational_unit_id": scope.operational_unit_id,
                "planning_date": scope.planning_date,
                "timezone": scope.timezone,
            }
        )
        return _authority(
            scope=execution_scope,
            fencing_token=fencing_token,
        )


def _runtime(service=None):
    return ExecutionIntentRuntime(
        service=service or _service(),
        publication_provider=FixedPublicationProvider(),
        authority_provider=FixedAuthorityProvider(),
        clock=lambda: NOW,
    )


def test_runtime_composes_contracts_but_does_not_create_attempts():
    result = _runtime().create(_command())

    assert result.status is ExecutionIntentStatus.READY
    assert result.intent.attempt_reference is None


def test_read_only_endpoint_returns_current_intent_with_compact_payload():
    runtime = _runtime()
    created = runtime.create(_command())
    app.dependency_overrides[get_execution_intent_runtime] = lambda: runtime
    try:
        response = TestClient(app).get(
            "/api/runtime/execution-intent",
            params={
                "organization_id": SCOPE.organization_id,
                "operational_unit_id": SCOPE.operational_unit_id,
                "planning_date": SCOPE.planning_date.isoformat(),
                "timezone": SCOPE.timezone,
                "publication_id": SCOPE.publication_id,
                "publication_version": SCOPE.publication_version,
                "execution_mode": SCOPE.execution_mode.value,
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["intent"]["intent_id"] == str(
        created.intent.intent_id
    )
    assert len(response.content) < 2 * 1024


def test_endpoint_rejects_invalid_timezone_without_stack_trace():
    response = TestClient(app).get(
        "/api/runtime/execution-intent",
        params={
            "organization_id": SCOPE.organization_id,
            "operational_unit_id": SCOPE.operational_unit_id,
            "planning_date": SCOPE.planning_date.isoformat(),
            "timezone": "invalid/timezone",
            "publication_id": SCOPE.publication_id,
            "publication_version": SCOPE.publication_version,
            "execution_mode": SCOPE.execution_mode.value,
        },
    )

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == (
        "INVALID_EXECUTION_INTENT_SCOPE"
    )
    assert "traceback" not in response.text.lower()


def test_openapi_exposes_exactly_one_read_only_execution_intent_operation():
    operation = app.openapi()["paths"]["/api/runtime/execution-intent"]

    assert set(operation) == {"get"}


def test_creation_logic_and_repository_meet_warm_latency_targets():
    repository = ExecutionIntentRepositorySQL()
    repository_samples = []
    creation_samples = []
    for index in range(30):
        scope = SCOPE.model_copy(
            update={"publication_id": f"publication-perf-{index}"}
        )
        service = _service(MemoryExecutionIntentRepository())
        started = perf_counter()
        result = service.create(
            command=_command(
                scope=scope,
                idempotency_key=f"intent-performance-{index:04d}",
            ),
            publication=_publication(scope=scope),
            authority=_authority(scope=scope),
        )
        creation_samples.append(perf_counter() - started)
        assert result.status is ExecutionIntentStatus.READY

    stored = _create(_service(repository)).intent
    repository.get_by_key(stored.intent_key)
    for _ in range(50):
        started = perf_counter()
        repository.get_by_key(stored.intent_key)
        repository_samples.append(perf_counter() - started)

    assert median(creation_samples) < 0.015
    assert median(repository_samples) < 0.020
