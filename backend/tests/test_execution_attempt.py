from datetime import UTC, date, datetime
from statistics import median
from time import perf_counter

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.api.dependencies.execution_attempt import (
    get_execution_attempt_runtime,
)
from app.core.database import db_session
from app.domain.execution_attempt import (
    ExecutionAttemptCommand,
    ExecutionAttemptId,
    ExecutionAttemptMode,
    ExecutionAttemptRepositoryConflictError,
    ExecutionAttemptScope,
    ExecutionAttemptSeriesScope,
    ExecutionAttemptService,
    ExecutionAttemptStatus,
    ExecutionAttemptValidator,
    ExecutionAttemptVersion,
    ExecutionAttemptVersionError,
    LockState,
)
from app.domain.execution_intent import (
    ExecutionIntentMode,
    ExecutionIntentStatus,
    ExecutionPublicationStatus,
)
from app.domain.runtime_authority import (
    AuthorityDecisionId,
    AuthorityResolutionState,
)
from app.main import app
from app.repositories.execution_attempt_repository import (
    ExecutionAttemptRepositorySQL,
)
from app.runtime.execution_attempt import ExecutionAttemptRuntime
from test_execution_intent import (
    NOW,
    SCOPE as INTENT_SCOPE,
    _authority,
    _create as create_intent,
    _publication,
    _service as intent_service,
)


class Identifiers:
    def __init__(self) -> None:
        self.value = 0

    def __call__(self) -> str:
        self.value += 1
        return f"{self.value:032d}"


def _intent(*, status=ExecutionIntentStatus.READY, mode=None):
    scope = INTENT_SCOPE
    if mode is not None:
        scope = scope.model_copy(update={"execution_mode": mode})
    intent = create_intent(intent_service(), scope=scope).intent
    if status is not ExecutionIntentStatus.READY:
        intent = intent.model_copy(update={"status": status})
    return intent


def _series_scope(intent) -> ExecutionAttemptSeriesScope:
    return ExecutionAttemptSeriesScope(
        organization_id=intent.scope.organization_id,
        operational_unit_id=intent.scope.operational_unit_id,
        planning_date=intent.scope.planning_date,
        timezone=intent.scope.timezone,
        execution_intent_id=intent.intent_id,
    )


def _command(
    intent,
    *,
    expected_intent_version: int | None = None,
    fencing_token: int = 7,
) -> ExecutionAttemptCommand:
    return ExecutionAttemptCommand(
        series_scope=_series_scope(intent),
        expected_intent_version=(
            expected_intent_version
            if expected_intent_version is not None
            else int(intent.version)
        ),
        authority_decision_id=AuthorityDecisionId("authority-a"),
        fencing_token=fencing_token,
        actor="attempt-operator",
    )


def _service(repository=None) -> ExecutionAttemptService:
    return ExecutionAttemptService(
        repository=repository or ExecutionAttemptRepositorySQL(),
        validator=ExecutionAttemptValidator(),
        clock=lambda: NOW,
        identifier_factory=Identifiers(),
    )


def _create_attempt(
    *,
    service=None,
    intent=None,
    publication=None,
    authority=None,
    command=None,
):
    selected_intent = intent or _intent()
    return (service or _service()).create(
        command=command or _command(selected_intent),
        intent=selected_intent,
        publication=publication or _publication(scope=selected_intent.scope),
        authority=authority or _authority(scope=selected_intent.scope),
    )


def _abort(repository, attempt):
    aborted = attempt.model_copy(
        update={
            "version": ExecutionAttemptVersion(int(attempt.version) + 1),
            "status": ExecutionAttemptStatus.ABORTED,
        }
    )
    repository.append(aborted)
    return aborted


def test_attempt_contract_is_immutable_and_excludes_runtime_states():
    result = _create_attempt()

    assert {status.value for status in ExecutionAttemptStatus} == {
        "PENDING",
        "LOCK_ACQUIRED",
        "READY_TO_EXECUTE",
        "ABORTED",
        "REJECTED",
    }
    assert {mode.value for mode in ExecutionAttemptMode} == {
        "NORMAL",
        "SHADOW",
        "VERIFY",
    }
    assert not {
        "RUNNING",
        "SUCCESS",
        "FAILED",
        "COMPLETED",
        "ROLLBACK",
    }.intersection(status.value for status in ExecutionAttemptStatus)
    with pytest.raises(ValidationError):
        result.attempt.status = ExecutionAttemptStatus.LOCK_ACQUIRED


def test_valid_attempt_is_pending_without_operational_or_real_lock_effects():
    result = _create_attempt()

    assert result.status is ExecutionAttemptStatus.PENDING
    assert result.attempt.scope.attempt_number == 1
    assert result.attempt.lock_state is LockState.AVAILABLE
    assert result.attempt.lock_token is None
    assert result.attempt.lock_owner is None
    assert result.validation.allowed is True
    assert "nessun lock distribuito" in (
        result.attempt.lock_diagnostics.items[0].message
    )


def test_authority_no_write_rejects_without_persisting_attempt():
    intent = _intent()
    repository = ExecutionAttemptRepositorySQL()
    result = _create_attempt(
        service=_service(repository),
        intent=intent,
        authority=_authority(
            scope=intent.scope,
            state=AuthorityResolutionState.NO_WRITE,
        ),
    )

    assert result.status is ExecutionAttemptStatus.REJECTED
    assert result.attempt is None
    assert repository.history(_series_scope(intent)).total == 0
    assert "Authority non valida." in {
        item.message for item in result.diagnostics.items
    }


@pytest.mark.parametrize(
    "status",
    [
        ExecutionIntentStatus.LOCKED,
        ExecutionIntentStatus.CANCELLED,
        ExecutionIntentStatus.SUPERSEDED,
        ExecutionIntentStatus.REJECTED,
    ],
)
def test_intent_not_ready_is_rejected(status):
    intent = _intent(status=status)
    result = _create_attempt(intent=intent)

    assert result.status is ExecutionAttemptStatus.REJECTED
    assert "Execution Intent non READY." in {
        item.message for item in result.diagnostics.items
    }


def test_cancelled_intent_has_explicit_diagnostic():
    intent = _intent(status=ExecutionIntentStatus.CANCELLED)
    result = _create_attempt(intent=intent)

    assert "Execution Intent cancellato." in {
        item.message for item in result.diagnostics.items
    }


@pytest.mark.parametrize(
    "publication_status",
    [
        ExecutionPublicationStatus.SUPERSEDED,
        ExecutionPublicationStatus.REVOKED,
    ],
)
def test_invalid_publication_is_rejected(publication_status):
    intent = _intent()
    result = _create_attempt(
        intent=intent,
        publication=_publication(
            scope=intent.scope,
            status=publication_status,
        ),
    )

    assert result.status is ExecutionAttemptStatus.REJECTED
    assert "Publication non valida." in {
        item.message for item in result.diagnostics.items
    }


def test_intent_version_mismatch_is_rejected():
    intent = _intent()
    result = _create_attempt(
        intent=intent,
        command=_command(
            intent,
            expected_intent_version=int(intent.version) + 1,
        ),
    )

    assert result.status is ExecutionAttemptStatus.REJECTED
    assert "Version mismatch." in {
        item.message for item in result.diagnostics.items
    }


def test_fencing_mismatch_is_rejected():
    intent = _intent()
    result = _create_attempt(
        intent=intent,
        command=_command(intent, fencing_token=6),
        authority=_authority(scope=intent.scope, fencing_token=7),
    )

    assert result.status is ExecutionAttemptStatus.REJECTED
    assert "Fencing obsoleto." in {
        item.message for item in result.diagnostics.items
    }


def test_rollback_intent_mode_is_rejected_without_rollback_runtime():
    intent = _intent(mode=ExecutionIntentMode.ROLLBACK)
    result = _create_attempt(intent=intent)

    assert result.status is ExecutionAttemptStatus.REJECTED
    assert "Mode Intent non supportato per Execution Attempt." in {
        item.message for item in result.diagnostics.items
    }


def test_active_attempt_blocks_parallel_attempt_with_lock_diagnostic():
    intent = _intent()
    service = _service()
    first = _create_attempt(service=service, intent=intent)
    second = _create_attempt(service=service, intent=intent)

    assert first.status is ExecutionAttemptStatus.PENDING
    assert second.status is ExecutionAttemptStatus.REJECTED
    assert "Lock non disponibile." in {
        item.message for item in second.diagnostics.items
    }


def test_attempt_number_increments_after_previous_attempt_is_aborted():
    intent = _intent()
    repository = ExecutionAttemptRepositorySQL()
    service = _service(repository)
    first = _create_attempt(service=service, intent=intent).attempt
    _abort(repository, first)

    second = _create_attempt(service=service, intent=intent).attempt

    assert first.scope.attempt_number == 1
    assert second.scope.attempt_number == 2
    assert repository.next_attempt_number(_series_scope(intent)) == 3


def test_repository_is_append_only_and_history_preserves_versions():
    intent = _intent()
    repository = ExecutionAttemptRepositorySQL()
    first = _create_attempt(
        service=_service(repository),
        intent=intent,
    ).attempt
    aborted = _abort(repository, first)

    history = repository.history(_series_scope(intent))
    assert history.total == 2
    assert [int(item.version) for item in history.attempts] == [2, 1]
    assert repository.get_current(first.scope) == aborted
    with db_session() as conn:
        rows = conn.execute(
            """
            SELECT version, status
            FROM runtime_execution_attempts
            WHERE attempt_id = ?
            ORDER BY version
            """,
            (str(first.attempt_id),),
        ).fetchall()
    assert [(row["version"], row["status"]) for row in rows] == [
        (1, "PENDING"),
        (2, "ABORTED"),
    ]


def test_repository_rejects_version_gap_and_scope_mutation():
    repository = ExecutionAttemptRepositorySQL()
    attempt = _create_attempt(service=_service(repository)).attempt

    with pytest.raises(ExecutionAttemptVersionError):
        repository.append(
            attempt.model_copy(
                update={
                    "version": ExecutionAttemptVersion(3),
                    "status": ExecutionAttemptStatus.ABORTED,
                }
            )
        )
    changed_scope = attempt.scope.model_copy(update={"attempt_number": 2})
    with pytest.raises(ExecutionAttemptRepositoryConflictError):
        repository.append(
            attempt.model_copy(
                update={
                    "version": ExecutionAttemptVersion(2),
                    "scope": changed_scope,
                    "status": ExecutionAttemptStatus.ABORTED,
                }
            )
        )
    with pytest.raises(ExecutionAttemptRepositoryConflictError):
        repository.append(
            attempt.model_copy(
                update={
                    "version": ExecutionAttemptVersion(2),
                    "status": ExecutionAttemptStatus.ABORTED,
                    "actor": "different-actor",
                }
            )
        )


def _runtime(service=None):
    return ExecutionAttemptRuntime(
        service=service or _service(),
        clock=lambda: NOW,
    )


def test_runtime_only_prepares_attempt_contract():
    intent = _intent()
    result = _runtime().create(
        command=_command(intent),
        intent=intent,
        publication=_publication(scope=intent.scope),
        authority=_authority(scope=intent.scope),
    )

    assert result.attempt.status is ExecutionAttemptStatus.PENDING
    assert result.attempt.lock_state is LockState.AVAILABLE


def test_read_only_endpoint_returns_attempt_with_compact_payload():
    intent = _intent()
    runtime = _runtime()
    created = runtime.create(
        command=_command(intent),
        intent=intent,
        publication=_publication(scope=intent.scope),
        authority=_authority(scope=intent.scope),
    )
    app.dependency_overrides[get_execution_attempt_runtime] = lambda: runtime
    try:
        response = TestClient(app).get(
            "/api/runtime/execution-attempt",
            params={
                "organization_id": intent.scope.organization_id,
                "operational_unit_id": intent.scope.operational_unit_id,
                "planning_date": intent.scope.planning_date.isoformat(),
                "timezone": intent.scope.timezone,
                "execution_intent_id": str(intent.intent_id),
                "attempt_number": 1,
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["attempt"]["attempt_id"] == str(
        created.attempt.attempt_id
    )
    assert len(response.content) < 2 * 1024


def test_endpoint_rejects_invalid_timezone_without_stack_trace():
    response = TestClient(app).get(
        "/api/runtime/execution-attempt",
        params={
            "organization_id": "organization-a",
            "operational_unit_id": "unit-a",
            "planning_date": date(2026, 7, 23).isoformat(),
            "timezone": "invalid/timezone",
            "execution_intent_id": "intent-a",
            "attempt_number": 1,
        },
    )

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == (
        "INVALID_EXECUTION_ATTEMPT_SCOPE"
    )
    assert "traceback" not in response.text.lower()


def test_openapi_exposes_exactly_one_read_only_attempt_operation():
    operation = app.openapi()["paths"]["/api/runtime/execution-attempt"]

    assert set(operation) == {"get"}


def test_validation_and_repository_meet_warm_latency_targets():
    intent = _intent()
    publication = _publication(scope=intent.scope)
    authority = _authority(scope=intent.scope)
    command = _command(intent)
    validator = ExecutionAttemptValidator()
    validation_samples = []
    for _ in range(200):
        started = perf_counter()
        result = validator.validate(
            command=command,
            intent=intent,
            publication=publication,
            authority=authority,
            active_attempt=None,
            evaluated_at=NOW,
        )
        validation_samples.append(perf_counter() - started)
        assert result.allowed is True

    repository = ExecutionAttemptRepositorySQL()
    stored = _create_attempt(
        service=_service(repository),
        intent=intent,
    ).attempt
    repository.get_current(stored.scope)
    repository_samples = []
    for _ in range(50):
        started = perf_counter()
        repository.get_current(stored.scope)
        repository_samples.append(perf_counter() - started)

    assert median(validation_samples) < 0.015
    assert median(repository_samples) < 0.020
