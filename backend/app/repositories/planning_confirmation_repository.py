import json
import sqlite3

from app.core.database import db_session
from app.domain.core_language import OperationalUnit
from app.domain.planning_confirmation import (
    PlanningConfirmation,
    PlanningConfirmationAlreadyExistsError,
    PlanningConfirmationHistory,
    PlanningConfirmationResult,
    PlanningConfirmationScope,
)


def init_schema() -> None:
    with db_session() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS planning_confirmations (
                confirmation_id TEXT PRIMARY KEY,
                organization_id TEXT NOT NULL,
                operational_unit_id TEXT NOT NULL,
                operational_unit_name TEXT,
                planning_date TEXT NOT NULL,
                state TEXT NOT NULL,
                version INTEGER NOT NULL,
                draft_id TEXT NOT NULL,
                draft_version INTEGER NOT NULL,
                draft_name TEXT NOT NULL,
                draft_note TEXT,
                readiness_status TEXT NOT NULL,
                readiness_score INTEGER NOT NULL,
                envelope_version TEXT NOT NULL,
                envelope_fingerprint TEXT NOT NULL,
                fingerprint TEXT NOT NULL UNIQUE,
                actor TEXT NOT NULL,
                confirmed_at TEXT NOT NULL,
                validation TEXT NOT NULL,
                FOREIGN KEY (draft_id) REFERENCES planning_drafts(draft_id),
                UNIQUE (
                    organization_id,
                    operational_unit_id,
                    planning_date
                )
            );

            CREATE INDEX IF NOT EXISTS idx_planning_confirmation_history
                ON planning_confirmations (
                    organization_id,
                    operational_unit_id,
                    planning_date,
                    confirmed_at DESC
                );
            """
        )


def _scope_from_row(row) -> PlanningConfirmationScope:
    return PlanningConfirmationScope(
        organization_id=row["organization_id"],
        operational_unit=OperationalUnit(
            external_identifier=row["operational_unit_id"],
            name=row["operational_unit_name"],
        ),
        planning_date=row["planning_date"],
    )


def _confirmation_from_row(row) -> PlanningConfirmation:
    return PlanningConfirmation(
        confirmation_id=row["confirmation_id"],
        scope=_scope_from_row(row),
        state=row["state"],
        version=row["version"],
        draft_id=row["draft_id"],
        draft_version=row["draft_version"],
        draft_name=row["draft_name"],
        draft_note=row["draft_note"],
        readiness_status=row["readiness_status"],
        readiness_score=row["readiness_score"],
        envelope_version=row["envelope_version"],
        envelope_fingerprint=row["envelope_fingerprint"],
        fingerprint=row["fingerprint"],
        actor=row["actor"],
        confirmed_at=row["confirmed_at"],
        validation=PlanningConfirmationResult.model_validate_json(
            row["validation"]
        ),
    )


class SqlPlanningConfirmationRepository:
    def get_current(
        self,
        scope: PlanningConfirmationScope,
    ) -> PlanningConfirmation | None:
        with db_session() as conn:
            row = conn.execute(
                """
                SELECT *
                FROM planning_confirmations
                WHERE organization_id = ?
                  AND operational_unit_id = ?
                  AND planning_date = ?
                ORDER BY version DESC
                LIMIT 1
                """,
                (
                    scope.organization_id,
                    scope.operational_unit.external_identifier,
                    scope.planning_date.isoformat(),
                ),
            ).fetchone()
        return _confirmation_from_row(row) if row else None

    def get_history(
        self,
        scope: PlanningConfirmationScope,
        *,
        limit: int = 100,
    ) -> PlanningConfirmationHistory:
        bounded_limit = max(1, min(limit, 100))
        parameters = (
            scope.organization_id,
            scope.operational_unit.external_identifier,
            scope.planning_date.isoformat(),
        )
        with db_session() as conn:
            count = conn.execute(
                """
                SELECT COUNT(*) AS total
                FROM planning_confirmations
                WHERE organization_id = ?
                  AND operational_unit_id = ?
                  AND planning_date = ?
                """,
                parameters,
            ).fetchone()
            rows = conn.execute(
                """
                SELECT *
                FROM planning_confirmations
                WHERE organization_id = ?
                  AND operational_unit_id = ?
                  AND planning_date = ?
                ORDER BY confirmed_at DESC, version DESC
                LIMIT ?
                """,
                (*parameters, bounded_limit),
            ).fetchall()
        return PlanningConfirmationHistory(
            scope=scope,
            total=int(count["total"]),
            confirmations=tuple(
                _confirmation_from_row(row) for row in rows
            ),
        )

    def next_version(self, scope: PlanningConfirmationScope) -> int:
        with db_session() as conn:
            row = conn.execute(
                """
                SELECT MAX(version) AS latest
                FROM planning_confirmations
                WHERE organization_id = ?
                  AND operational_unit_id = ?
                  AND planning_date = ?
                """,
                (
                    scope.organization_id,
                    scope.operational_unit.external_identifier,
                    scope.planning_date.isoformat(),
                ),
            ).fetchone()
        return int(row["latest"] or 0) + 1

    def add(self, confirmation: PlanningConfirmation) -> None:
        try:
            with db_session() as conn:
                conn.execute(
                    """
                    INSERT INTO planning_confirmations (
                        confirmation_id, organization_id,
                        operational_unit_id, operational_unit_name,
                        planning_date, state, version, draft_id,
                        draft_version, draft_name, draft_note,
                        readiness_status, readiness_score,
                        envelope_version, envelope_fingerprint,
                        fingerprint, actor, confirmed_at, validation
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        confirmation.confirmation_id,
                        confirmation.scope.organization_id,
                        confirmation.scope.operational_unit.external_identifier,
                        confirmation.scope.operational_unit.name,
                        confirmation.scope.planning_date.isoformat(),
                        confirmation.state.value,
                        confirmation.version,
                        confirmation.draft_id,
                        confirmation.draft_version,
                        confirmation.draft_name,
                        confirmation.draft_note,
                        confirmation.readiness_status.value,
                        confirmation.readiness_score,
                        confirmation.envelope_version,
                        confirmation.envelope_fingerprint,
                        confirmation.fingerprint,
                        confirmation.actor,
                        confirmation.confirmed_at.isoformat(),
                        json.dumps(
                            confirmation.validation.model_dump(mode="json"),
                            ensure_ascii=True,
                            separators=(",", ":"),
                            sort_keys=True,
                        ),
                    ),
                )
        except sqlite3.IntegrityError as exc:
            raise PlanningConfirmationAlreadyExistsError(
                "Esiste gia un Confirmed Plan per questo contesto."
            ) from exc
