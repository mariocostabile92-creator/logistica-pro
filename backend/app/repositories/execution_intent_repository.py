import sqlite3

from app.core.database import db_session
from app.domain.execution_intent import (
    ExecutionAttemptReference,
    ExecutionIntent,
    ExecutionIntentId,
    ExecutionIntentKey,
    ExecutionIntentRepositoryConflictError,
    ExecutionIntentScope,
    ExecutionIntentVersion,
    ExecutionIntentVersionError,
)
from app.domain.runtime_authority import AuthorityDecisionId


def init_schema() -> None:
    with db_session() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS runtime_execution_intents (
                intent_id TEXT NOT NULL,
                version INTEGER NOT NULL,
                intent_key TEXT NOT NULL,
                organization_id TEXT NOT NULL,
                operational_unit_id TEXT NOT NULL,
                planning_date TEXT NOT NULL,
                timezone TEXT NOT NULL,
                publication_id TEXT NOT NULL,
                publication_version INTEGER NOT NULL,
                execution_mode TEXT NOT NULL,
                status TEXT NOT NULL,
                publication_fingerprint TEXT NOT NULL,
                authority_decision_id TEXT NOT NULL,
                fencing_token INTEGER NOT NULL,
                idempotency_key TEXT NOT NULL,
                payload_fingerprint TEXT NOT NULL,
                actor TEXT NOT NULL,
                created_at TEXT NOT NULL,
                attempt_id TEXT,
                attempt_version INTEGER,
                PRIMARY KEY (intent_id, version),
                UNIQUE (intent_key, version),
                UNIQUE (organization_id, idempotency_key)
            );

            CREATE INDEX IF NOT EXISTS idx_execution_intent_scope
                ON runtime_execution_intents (
                    organization_id,
                    operational_unit_id,
                    planning_date,
                    timezone,
                    publication_id,
                    publication_version,
                    execution_mode,
                    version DESC
                );
            """
        )


def _intent_from_row(row) -> ExecutionIntent:
    attempt = None
    if row["attempt_id"] is not None:
        attempt = ExecutionAttemptReference(
            attempt_id=row["attempt_id"],
            attempt_version=row["attempt_version"],
        )
    return ExecutionIntent(
        intent_id=ExecutionIntentId(row["intent_id"]),
        intent_key=ExecutionIntentKey(row["intent_key"]),
        scope=ExecutionIntentScope(
            organization_id=row["organization_id"],
            operational_unit_id=row["operational_unit_id"],
            planning_date=row["planning_date"],
            timezone=row["timezone"],
            publication_id=row["publication_id"],
            publication_version=row["publication_version"],
            execution_mode=row["execution_mode"],
        ),
        version=ExecutionIntentVersion(row["version"]),
        status=row["status"],
        publication_fingerprint=row["publication_fingerprint"],
        authority_decision_id=AuthorityDecisionId(
            row["authority_decision_id"]
        ),
        fencing_token=row["fencing_token"],
        idempotency_key=row["idempotency_key"],
        payload_fingerprint=row["payload_fingerprint"],
        actor=row["actor"],
        created_at=row["created_at"],
        attempt_reference=attempt,
    )


def _scope_parameters(
    scope: ExecutionIntentScope,
) -> tuple[str, str, str, str, str, int, str]:
    return (
        scope.organization_id,
        scope.operational_unit_id,
        scope.planning_date.isoformat(),
        scope.timezone,
        scope.publication_id,
        scope.publication_version,
        scope.execution_mode.value,
    )


class ExecutionIntentRepositorySQL:
    def get_by_key(
        self,
        intent_key: ExecutionIntentKey,
    ) -> ExecutionIntent | None:
        with db_session() as conn:
            row = conn.execute(
                """
                SELECT *
                FROM runtime_execution_intents
                WHERE intent_key = ?
                ORDER BY version DESC
                LIMIT 1
                """,
                (str(intent_key),),
            ).fetchone()
        return _intent_from_row(row) if row else None

    def get_by_idempotency_key(
        self,
        *,
        organization_id: str,
        idempotency_key: str,
    ) -> ExecutionIntent | None:
        with db_session() as conn:
            row = conn.execute(
                """
                SELECT *
                FROM runtime_execution_intents
                WHERE organization_id = ?
                  AND idempotency_key = ?
                ORDER BY version DESC
                LIMIT 1
                """,
                (organization_id, idempotency_key),
            ).fetchone()
        return _intent_from_row(row) if row else None

    def list_for_scope(
        self,
        scope: ExecutionIntentScope,
    ) -> tuple[ExecutionIntent, ...]:
        with db_session() as conn:
            rows = conn.execute(
                """
                SELECT *
                FROM runtime_execution_intents
                WHERE organization_id = ?
                  AND operational_unit_id = ?
                  AND planning_date = ?
                  AND timezone = ?
                  AND publication_id = ?
                  AND publication_version = ?
                  AND execution_mode = ?
                ORDER BY version DESC, created_at DESC
                LIMIT 100
                """,
                _scope_parameters(scope),
            ).fetchall()
        return tuple(_intent_from_row(row) for row in rows)

    def append(self, intent: ExecutionIntent) -> None:
        try:
            with db_session() as conn:
                latest = conn.execute(
                    """
                    SELECT intent_id, MAX(version) AS latest_version
                    FROM runtime_execution_intents
                    WHERE intent_key = ?
                    GROUP BY intent_id
                    ORDER BY latest_version DESC
                    LIMIT 1
                    """,
                    (str(intent.intent_key),),
                ).fetchone()
                expected_version = int(
                    latest["latest_version"] if latest else 0
                ) + 1
                if int(intent.version) != expected_version:
                    raise ExecutionIntentVersionError(
                        "Execution Intent version must increase by exactly one."
                    )
                if latest and latest["intent_id"] != str(intent.intent_id):
                    raise ExecutionIntentRepositoryConflictError(
                        "Intent key cannot be assigned to another intent id."
                    )
                attempt = intent.attempt_reference
                conn.execute(
                    """
                    INSERT INTO runtime_execution_intents (
                        intent_id, version, intent_key,
                        organization_id, operational_unit_id,
                        planning_date, timezone,
                        publication_id, publication_version,
                        execution_mode, status,
                        publication_fingerprint,
                        authority_decision_id, fencing_token,
                        idempotency_key, payload_fingerprint,
                        actor, created_at,
                        attempt_id, attempt_version
                    )
                    VALUES (
                        ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                        ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
                    )
                    """,
                    (
                        str(intent.intent_id),
                        int(intent.version),
                        str(intent.intent_key),
                        *_scope_parameters(intent.scope),
                        intent.status.value,
                        intent.publication_fingerprint,
                        str(intent.authority_decision_id),
                        intent.fencing_token,
                        intent.idempotency_key,
                        intent.payload_fingerprint,
                        intent.actor,
                        intent.created_at.isoformat(),
                        attempt.attempt_id if attempt else None,
                        attempt.attempt_version if attempt else None,
                    ),
                )
        except sqlite3.IntegrityError as exc:
            raise ExecutionIntentRepositoryConflictError(
                "Execution Intent already exists or violates idempotency."
            ) from exc
