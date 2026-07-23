import json
import sqlite3

from app.core.database import db_session
from app.domain.execution_attempt import (
    ExecutionAttempt,
    ExecutionAttemptHistory,
    ExecutionAttemptId,
    ExecutionAttemptRepositoryConflictError,
    ExecutionAttemptScope,
    ExecutionAttemptSeriesScope,
    ExecutionAttemptStatus,
    ExecutionAttemptVersion,
    ExecutionAttemptVersionError,
    LockDiagnostics,
    LockOwner,
    LockState,
    LockToken,
)
from app.domain.execution_intent import ExecutionIntentId
from app.domain.runtime_authority import AuthorityDecisionId


def init_schema() -> None:
    with db_session() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS runtime_execution_attempts (
                attempt_id TEXT NOT NULL,
                version INTEGER NOT NULL,
                organization_id TEXT NOT NULL,
                operational_unit_id TEXT NOT NULL,
                planning_date TEXT NOT NULL,
                timezone TEXT NOT NULL,
                execution_intent_id TEXT NOT NULL,
                attempt_number INTEGER NOT NULL,
                mode TEXT NOT NULL,
                status TEXT NOT NULL,
                intent_version INTEGER NOT NULL,
                publication_id TEXT NOT NULL,
                publication_version INTEGER NOT NULL,
                publication_fingerprint TEXT NOT NULL,
                authority_decision_id TEXT NOT NULL,
                fencing_token INTEGER NOT NULL,
                actor TEXT NOT NULL,
                created_at TEXT NOT NULL,
                lock_state TEXT NOT NULL,
                lock_token TEXT,
                lock_owner TEXT,
                lock_diagnostics TEXT NOT NULL,
                PRIMARY KEY (attempt_id, version),
                UNIQUE (
                    execution_intent_id,
                    attempt_number,
                    version
                )
            );

            CREATE INDEX IF NOT EXISTS idx_execution_attempt_scope
                ON runtime_execution_attempts (
                    organization_id,
                    operational_unit_id,
                    planning_date,
                    timezone,
                    execution_intent_id,
                    attempt_number DESC,
                    version DESC
                );
            """
        )


def _attempt_from_row(row) -> ExecutionAttempt:
    lock_token = (
        LockToken(row["lock_token"])
        if row["lock_token"] is not None
        else None
    )
    lock_owner = (
        LockOwner(row["lock_owner"])
        if row["lock_owner"] is not None
        else None
    )
    return ExecutionAttempt(
        attempt_id=ExecutionAttemptId(row["attempt_id"]),
        scope=ExecutionAttemptScope(
            organization_id=row["organization_id"],
            operational_unit_id=row["operational_unit_id"],
            planning_date=row["planning_date"],
            timezone=row["timezone"],
            execution_intent_id=ExecutionIntentId(
                row["execution_intent_id"]
            ),
            attempt_number=row["attempt_number"],
        ),
        mode=row["mode"],
        version=ExecutionAttemptVersion(row["version"]),
        status=row["status"],
        intent_version=row["intent_version"],
        publication_id=row["publication_id"],
        publication_version=row["publication_version"],
        publication_fingerprint=row["publication_fingerprint"],
        authority_decision_id=AuthorityDecisionId(
            row["authority_decision_id"]
        ),
        fencing_token=row["fencing_token"],
        actor=row["actor"],
        created_at=row["created_at"],
        lock_state=LockState(row["lock_state"]),
        lock_token=lock_token,
        lock_owner=lock_owner,
        lock_diagnostics=LockDiagnostics.model_validate_json(
            row["lock_diagnostics"]
        ),
    )


def _series_parameters(
    scope: ExecutionAttemptSeriesScope,
) -> tuple[str, str, str, str, str]:
    return (
        scope.organization_id,
        scope.operational_unit_id,
        scope.planning_date.isoformat(),
        scope.timezone,
        str(scope.execution_intent_id),
    )


class ExecutionAttemptRepositorySQL:
    def get_current(
        self,
        scope: ExecutionAttemptScope,
    ) -> ExecutionAttempt | None:
        with db_session() as conn:
            row = conn.execute(
                """
                SELECT *
                FROM runtime_execution_attempts
                WHERE organization_id = ?
                  AND operational_unit_id = ?
                  AND planning_date = ?
                  AND timezone = ?
                  AND execution_intent_id = ?
                  AND attempt_number = ?
                ORDER BY version DESC
                LIMIT 1
                """,
                (*_series_parameters(scope.series_scope), scope.attempt_number),
            ).fetchone()
        return _attempt_from_row(row) if row else None

    def get_active(
        self,
        scope: ExecutionAttemptSeriesScope,
    ) -> ExecutionAttempt | None:
        with db_session() as conn:
            row = conn.execute(
                """
                WITH latest AS (
                    SELECT attempt_id, MAX(version) AS latest_version
                    FROM runtime_execution_attempts
                    WHERE organization_id = ?
                      AND operational_unit_id = ?
                      AND planning_date = ?
                      AND timezone = ?
                      AND execution_intent_id = ?
                    GROUP BY attempt_id
                )
                SELECT attempts.*
                FROM runtime_execution_attempts AS attempts
                JOIN latest
                  ON latest.attempt_id = attempts.attempt_id
                 AND latest.latest_version = attempts.version
                WHERE attempts.status IN (?, ?, ?)
                ORDER BY attempts.attempt_number DESC
                LIMIT 1
                """,
                (
                    *_series_parameters(scope),
                    ExecutionAttemptStatus.PENDING.value,
                    ExecutionAttemptStatus.LOCK_ACQUIRED.value,
                    ExecutionAttemptStatus.READY_TO_EXECUTE.value,
                ),
            ).fetchone()
        return _attempt_from_row(row) if row else None

    def history(
        self,
        scope: ExecutionAttemptSeriesScope,
        *,
        limit: int = 100,
    ) -> ExecutionAttemptHistory:
        bounded_limit = max(1, min(limit, 100))
        parameters = _series_parameters(scope)
        with db_session() as conn:
            count = conn.execute(
                """
                SELECT COUNT(*) AS total
                FROM runtime_execution_attempts
                WHERE organization_id = ?
                  AND operational_unit_id = ?
                  AND planning_date = ?
                  AND timezone = ?
                  AND execution_intent_id = ?
                """,
                parameters,
            ).fetchone()
            rows = conn.execute(
                """
                SELECT *
                FROM runtime_execution_attempts
                WHERE organization_id = ?
                  AND operational_unit_id = ?
                  AND planning_date = ?
                  AND timezone = ?
                  AND execution_intent_id = ?
                ORDER BY attempt_number DESC, version DESC
                LIMIT ?
                """,
                (*parameters, bounded_limit),
            ).fetchall()
        return ExecutionAttemptHistory(
            scope=scope,
            total=int(count["total"]),
            attempts=tuple(_attempt_from_row(row) for row in rows),
        )

    def next_attempt_number(
        self,
        scope: ExecutionAttemptSeriesScope,
    ) -> int:
        with db_session() as conn:
            row = conn.execute(
                """
                SELECT MAX(attempt_number) AS latest
                FROM runtime_execution_attempts
                WHERE organization_id = ?
                  AND operational_unit_id = ?
                  AND planning_date = ?
                  AND timezone = ?
                  AND execution_intent_id = ?
                """,
                _series_parameters(scope),
            ).fetchone()
        return int(row["latest"] or 0) + 1

    def append(self, attempt: ExecutionAttempt) -> None:
        try:
            with db_session() as conn:
                latest = conn.execute(
                    """
                    SELECT *
                    FROM runtime_execution_attempts
                    WHERE attempt_id = ?
                    ORDER BY version DESC
                    LIMIT 1
                    """,
                    (str(attempt.attempt_id),),
                ).fetchone()
                expected_version = int(latest["version"] if latest else 0) + 1
                if int(attempt.version) != expected_version:
                    raise ExecutionAttemptVersionError(
                        "Execution Attempt version must increase by exactly one."
                    )
                if latest:
                    previous = _attempt_from_row(latest)
                    if previous.scope.identity != attempt.scope.identity:
                        raise ExecutionAttemptRepositoryConflictError(
                            "Attempt scope and number are immutable."
                        )
                    immutable_previous = (
                        previous.mode,
                        previous.intent_version,
                        previous.publication_id,
                        previous.publication_version,
                        previous.publication_fingerprint,
                        previous.authority_decision_id,
                        previous.fencing_token,
                        previous.actor,
                        previous.created_at,
                    )
                    immutable_current = (
                        attempt.mode,
                        attempt.intent_version,
                        attempt.publication_id,
                        attempt.publication_version,
                        attempt.publication_fingerprint,
                        attempt.authority_decision_id,
                        attempt.fencing_token,
                        attempt.actor,
                        attempt.created_at,
                    )
                    if immutable_previous != immutable_current:
                        raise ExecutionAttemptRepositoryConflictError(
                            "Attempt contract fields are immutable."
                        )
                conn.execute(
                    """
                    INSERT INTO runtime_execution_attempts (
                        attempt_id, version,
                        organization_id, operational_unit_id,
                        planning_date, timezone,
                        execution_intent_id, attempt_number,
                        mode, status, intent_version,
                        publication_id, publication_version,
                        publication_fingerprint,
                        authority_decision_id, fencing_token,
                        actor, created_at,
                        lock_state, lock_token, lock_owner,
                        lock_diagnostics
                    )
                    VALUES (
                        ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                        ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
                    )
                    """,
                    (
                        str(attempt.attempt_id),
                        int(attempt.version),
                        *_series_parameters(attempt.scope.series_scope),
                        attempt.scope.attempt_number,
                        attempt.mode.value,
                        attempt.status.value,
                        attempt.intent_version,
                        attempt.publication_id,
                        attempt.publication_version,
                        attempt.publication_fingerprint,
                        str(attempt.authority_decision_id),
                        attempt.fencing_token,
                        attempt.actor,
                        attempt.created_at.isoformat(),
                        attempt.lock_state.value,
                        str(attempt.lock_token) if attempt.lock_token else None,
                        str(attempt.lock_owner) if attempt.lock_owner else None,
                        json.dumps(
                            attempt.lock_diagnostics.model_dump(mode="json"),
                            ensure_ascii=False,
                            separators=(",", ":"),
                        ),
                    ),
                )
        except sqlite3.IntegrityError as exc:
            raise ExecutionAttemptRepositoryConflictError(
                "Execution Attempt number or version already exists."
            ) from exc
