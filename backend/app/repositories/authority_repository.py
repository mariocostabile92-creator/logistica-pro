import sqlite3

from app.core.database import db_session
from app.domain.runtime_authority import (
    AuthorityDecision,
    AuthorityDecisionId,
    AuthorityDecisionVersion,
    AuthorityFencingTokenError,
    AuthorityRepositoryConflictError,
    AuthorityScope,
    AuthorityVersionError,
)


def init_schema() -> None:
    with db_session() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS runtime_authority_decisions (
                decision_id TEXT PRIMARY KEY,
                organization_id TEXT NOT NULL,
                operational_unit_id TEXT NOT NULL,
                planning_date TEXT NOT NULL,
                timezone TEXT NOT NULL,
                mode TEXT NOT NULL,
                status TEXT NOT NULL,
                priority INTEGER NOT NULL,
                version INTEGER NOT NULL,
                valid_from TEXT NOT NULL,
                valid_until TEXT NOT NULL,
                reason TEXT NOT NULL,
                actor TEXT NOT NULL,
                created_at TEXT NOT NULL,
                fencing_token INTEGER NOT NULL,
                UNIQUE (
                    organization_id,
                    operational_unit_id,
                    planning_date,
                    timezone,
                    version
                ),
                UNIQUE (
                    organization_id,
                    operational_unit_id,
                    planning_date,
                    timezone,
                    fencing_token
                )
            );

            CREATE INDEX IF NOT EXISTS idx_runtime_authority_scope
                ON runtime_authority_decisions (
                    organization_id,
                    operational_unit_id,
                    planning_date,
                    timezone,
                    version DESC
                );
            """
        )


def _decision_from_row(row) -> AuthorityDecision:
    return AuthorityDecision(
        decision_id=AuthorityDecisionId(row["decision_id"]),
        scope=AuthorityScope(
            organization_id=row["organization_id"],
            operational_unit_id=row["operational_unit_id"],
            planning_date=row["planning_date"],
            timezone=row["timezone"],
        ),
        mode=row["mode"],
        status=row["status"],
        priority=row["priority"],
        version=AuthorityDecisionVersion(row["version"]),
        valid_from=row["valid_from"],
        valid_until=row["valid_until"],
        reason=row["reason"],
        actor=row["actor"],
        created_at=row["created_at"],
        fencing_token=row["fencing_token"],
    )


def _scope_parameters(scope: AuthorityScope) -> tuple[str, str, str, str]:
    return (
        scope.organization_id,
        scope.operational_unit_id,
        scope.planning_date.isoformat(),
        scope.timezone,
    )


class AuthorityRepositorySQL:
    def list_for_scope(
        self,
        scope: AuthorityScope,
    ) -> tuple[AuthorityDecision, ...]:
        with db_session() as conn:
            rows = conn.execute(
                """
                SELECT *
                FROM runtime_authority_decisions
                WHERE organization_id = ?
                  AND operational_unit_id = ?
                  AND planning_date = ?
                  AND timezone = ?
                ORDER BY version DESC, fencing_token DESC
                LIMIT 100
                """,
                _scope_parameters(scope),
            ).fetchall()
        return tuple(_decision_from_row(row) for row in rows)

    def get_by_id(
        self,
        decision_id: AuthorityDecisionId,
    ) -> AuthorityDecision | None:
        with db_session() as conn:
            row = conn.execute(
                """
                SELECT *
                FROM runtime_authority_decisions
                WHERE decision_id = ?
                """,
                (str(decision_id),),
            ).fetchone()
        return _decision_from_row(row) if row else None

    def latest_fencing_token(self, scope: AuthorityScope) -> int:
        with db_session() as conn:
            row = conn.execute(
                """
                SELECT MAX(fencing_token) AS latest
                FROM runtime_authority_decisions
                WHERE organization_id = ?
                  AND operational_unit_id = ?
                  AND planning_date = ?
                  AND timezone = ?
                """,
                _scope_parameters(scope),
            ).fetchone()
        return int(row["latest"] or 0)

    def add(self, decision: AuthorityDecision) -> None:
        scope_parameters = _scope_parameters(decision.scope)
        try:
            with db_session() as conn:
                latest = conn.execute(
                    """
                    SELECT
                        MAX(version) AS latest_version,
                        MAX(fencing_token) AS latest_token
                    FROM runtime_authority_decisions
                    WHERE organization_id = ?
                      AND operational_unit_id = ?
                      AND planning_date = ?
                      AND timezone = ?
                    """,
                    scope_parameters,
                ).fetchone()
                expected_version = int(latest["latest_version"] or 0) + 1
                expected_token = int(latest["latest_token"] or 0) + 1
                if int(decision.version) != expected_version:
                    raise AuthorityVersionError(
                        "Authority version must increase by exactly one."
                    )
                if decision.fencing_token != expected_token:
                    raise AuthorityFencingTokenError(
                        "Authority fencing token must increase by exactly one."
                    )
                conn.execute(
                    """
                    INSERT INTO runtime_authority_decisions (
                        decision_id,
                        organization_id,
                        operational_unit_id,
                        planning_date,
                        timezone,
                        mode,
                        status,
                        priority,
                        version,
                        valid_from,
                        valid_until,
                        reason,
                        actor,
                        created_at,
                        fencing_token
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        str(decision.decision_id),
                        *scope_parameters,
                        decision.mode.value,
                        decision.status.value,
                        decision.priority,
                        int(decision.version),
                        decision.valid_from.isoformat(),
                        decision.valid_until.isoformat(),
                        decision.reason,
                        decision.actor,
                        decision.created_at.isoformat(),
                        decision.fencing_token,
                    ),
                )
        except sqlite3.IntegrityError as exc:
            raise AuthorityRepositoryConflictError(
                "Authority decision already exists or violates scope ordering."
            ) from exc
