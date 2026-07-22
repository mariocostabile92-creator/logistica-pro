import json
import sqlite3

from app.core.database import db_session
from app.domain.core_language import OperationalUnit
from app.domain.planning_publication import (
    PlanningPublication,
    PlanningPublicationAlreadyExistsError,
    PlanningPublicationHistory,
    PlanningPublicationResult,
    PlanningPublicationScope,
)


def init_schema() -> None:
    with db_session() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS planning_publications (
                publication_id TEXT PRIMARY KEY,
                organization_id TEXT NOT NULL,
                operational_unit_id TEXT NOT NULL,
                operational_unit_name TEXT,
                planning_date TEXT NOT NULL,
                state TEXT NOT NULL,
                version INTEGER NOT NULL,
                confirmation_id TEXT NOT NULL,
                confirmation_version INTEGER NOT NULL,
                confirmation_fingerprint TEXT NOT NULL,
                fingerprint TEXT NOT NULL UNIQUE,
                actor TEXT NOT NULL,
                published_at TEXT NOT NULL,
                validation TEXT NOT NULL,
                FOREIGN KEY (confirmation_id)
                    REFERENCES planning_confirmations(confirmation_id),
                UNIQUE (
                    organization_id,
                    operational_unit_id,
                    planning_date
                )
            );

            CREATE INDEX IF NOT EXISTS idx_planning_publication_history
                ON planning_publications (
                    organization_id,
                    operational_unit_id,
                    planning_date,
                    published_at DESC
                );
            """
        )


def _scope_from_row(row) -> PlanningPublicationScope:
    return PlanningPublicationScope(
        organization_id=row["organization_id"],
        operational_unit=OperationalUnit(
            external_identifier=row["operational_unit_id"],
            name=row["operational_unit_name"],
        ),
        planning_date=row["planning_date"],
    )


def _publication_from_row(row) -> PlanningPublication:
    return PlanningPublication(
        publication_id=row["publication_id"],
        scope=_scope_from_row(row),
        state=row["state"],
        version=row["version"],
        confirmation_id=row["confirmation_id"],
        confirmation_version=row["confirmation_version"],
        confirmation_fingerprint=row["confirmation_fingerprint"],
        fingerprint=row["fingerprint"],
        actor=row["actor"],
        published_at=row["published_at"],
        validation=PlanningPublicationResult.model_validate_json(
            row["validation"]
        ),
    )


class SqlPlanningPublicationRepository:
    def get_current(
        self,
        scope: PlanningPublicationScope,
    ) -> PlanningPublication | None:
        with db_session() as conn:
            row = conn.execute(
                """
                SELECT *
                FROM planning_publications
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
        return _publication_from_row(row) if row else None

    def get_history(
        self,
        scope: PlanningPublicationScope,
        *,
        limit: int = 100,
    ) -> PlanningPublicationHistory:
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
                FROM planning_publications
                WHERE organization_id = ?
                  AND operational_unit_id = ?
                  AND planning_date = ?
                """,
                parameters,
            ).fetchone()
            rows = conn.execute(
                """
                SELECT *
                FROM planning_publications
                WHERE organization_id = ?
                  AND operational_unit_id = ?
                  AND planning_date = ?
                ORDER BY published_at DESC, version DESC
                LIMIT ?
                """,
                (*parameters, bounded_limit),
            ).fetchall()
        return PlanningPublicationHistory(
            scope=scope,
            total=int(count["total"]),
            publications=tuple(_publication_from_row(row) for row in rows),
        )

    def next_version(self, scope: PlanningPublicationScope) -> int:
        with db_session() as conn:
            row = conn.execute(
                """
                SELECT MAX(version) AS latest
                FROM planning_publications
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

    def add(self, publication: PlanningPublication) -> None:
        try:
            with db_session() as conn:
                conn.execute(
                    """
                    INSERT INTO planning_publications (
                        publication_id, organization_id,
                        operational_unit_id, operational_unit_name,
                        planning_date, state, version, confirmation_id,
                        confirmation_version, confirmation_fingerprint,
                        fingerprint, actor, published_at, validation
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        publication.publication_id,
                        publication.scope.organization_id,
                        publication.scope.operational_unit.external_identifier,
                        publication.scope.operational_unit.name,
                        publication.scope.planning_date.isoformat(),
                        publication.state.value,
                        publication.version,
                        publication.confirmation_id,
                        publication.confirmation_version,
                        publication.confirmation_fingerprint,
                        publication.fingerprint,
                        publication.actor,
                        publication.published_at.isoformat(),
                        json.dumps(
                            publication.validation.model_dump(mode="json"),
                            ensure_ascii=True,
                            separators=(",", ":"),
                            sort_keys=True,
                        ),
                    ),
                )
        except sqlite3.IntegrityError as exc:
            raise PlanningPublicationAlreadyExistsError(
                "Esiste gia un Published Plan per questo contesto."
            ) from exc
