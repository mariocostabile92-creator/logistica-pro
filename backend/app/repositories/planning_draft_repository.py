import json
import sqlite3

from app.core.database import db_session
from app.domain.core_language import OperationalUnit
from app.domain.planning_drafts import (
    PlanningDraft,
    PlanningDraftAlreadyExistsError,
    PlanningDraftChange,
    PlanningDraftChangeMetadata,
    PlanningDraftHistory,
    PlanningDraftMetadata,
    PlanningDraftScope,
    PlanningDraftSnapshot,
    PlanningDraftState,
    PlanningDraftVersion,
)


def init_schema() -> None:
    with db_session() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS planning_drafts (
                draft_id TEXT PRIMARY KEY,
                organization_id TEXT NOT NULL,
                operational_unit_id TEXT NOT NULL,
                operational_unit_name TEXT,
                planning_date TEXT NOT NULL,
                name TEXT NOT NULL,
                note TEXT,
                state TEXT NOT NULL,
                version INTEGER NOT NULL,
                version_created_at TEXT NOT NULL,
                version_created_by TEXT NOT NULL,
                restored_from_version INTEGER,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                deleted_at TEXT
            );

            CREATE UNIQUE INDEX IF NOT EXISTS idx_planning_drafts_active_scope
                ON planning_drafts (
                    organization_id,
                    operational_unit_id,
                    planning_date
                )
                WHERE deleted_at IS NULL;

            CREATE TABLE IF NOT EXISTS planning_draft_versions (
                snapshot_id TEXT PRIMARY KEY,
                draft_id TEXT NOT NULL,
                version INTEGER NOT NULL,
                state TEXT NOT NULL,
                name TEXT NOT NULL,
                note TEXT,
                created_at TEXT NOT NULL,
                created_by TEXT NOT NULL,
                restored_from_version INTEGER,
                FOREIGN KEY (draft_id) REFERENCES planning_drafts(draft_id)
                    ON DELETE CASCADE,
                UNIQUE (draft_id, version)
            );

            CREATE TABLE IF NOT EXISTS planning_draft_changes (
                change_id TEXT PRIMARY KEY,
                draft_id TEXT NOT NULL,
                change_type TEXT NOT NULL,
                from_version INTEGER,
                to_version INTEGER NOT NULL,
                actor TEXT NOT NULL,
                occurred_at TEXT NOT NULL,
                summary TEXT NOT NULL,
                metadata TEXT NOT NULL,
                FOREIGN KEY (draft_id) REFERENCES planning_drafts(draft_id)
                    ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_planning_draft_versions
                ON planning_draft_versions (draft_id, version DESC);
            CREATE INDEX IF NOT EXISTS idx_planning_draft_changes
                ON planning_draft_changes (draft_id, occurred_at DESC);
            """
        )


def _scope_from_row(row) -> PlanningDraftScope:
    return PlanningDraftScope(
        organization_id=row["organization_id"],
        operational_unit=OperationalUnit(
            external_identifier=row["operational_unit_id"],
            name=row["operational_unit_name"],
        ),
        planning_date=row["planning_date"],
    )


def _version_from_row(row) -> PlanningDraftVersion:
    return PlanningDraftVersion(
        number=row["version"],
        created_at=row["version_created_at"],
        created_by=row["version_created_by"],
        restored_from_version=row["restored_from_version"],
    )


def _draft_from_row(row) -> PlanningDraft:
    return PlanningDraft(
        draft_id=row["draft_id"],
        scope=_scope_from_row(row),
        metadata=PlanningDraftMetadata(
            name=row["name"],
            note=row["note"],
        ),
        state=row["state"],
        version=_version_from_row(row),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        deleted_at=row["deleted_at"],
    )


def _snapshot_from_row(row) -> PlanningDraftSnapshot:
    return PlanningDraftSnapshot(
        snapshot_id=row["snapshot_id"],
        draft_id=row["draft_id"],
        state=row["state"],
        version=PlanningDraftVersion(
            number=row["version"],
            created_at=row["created_at"],
            created_by=row["created_by"],
            restored_from_version=row["restored_from_version"],
        ),
        metadata=PlanningDraftMetadata(
            name=row["name"],
            note=row["note"],
        ),
    )


def _change_from_row(row) -> PlanningDraftChange:
    raw_metadata = json.loads(row["metadata"])
    return PlanningDraftChange(
        change_id=row["change_id"],
        draft_id=row["draft_id"],
        change_type=row["change_type"],
        from_version=row["from_version"],
        to_version=row["to_version"],
        actor=row["actor"],
        occurred_at=row["occurred_at"],
        summary=row["summary"],
        metadata=tuple(
            PlanningDraftChangeMetadata.model_validate(item)
            for item in raw_metadata
        ),
    )


def _insert_snapshot(conn, snapshot: PlanningDraftSnapshot) -> None:
    conn.execute(
        """
        INSERT INTO planning_draft_versions (
            snapshot_id, draft_id, version, state, name, note,
            created_at, created_by, restored_from_version
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            snapshot.snapshot_id,
            snapshot.draft_id,
            snapshot.version.number,
            snapshot.state.value,
            snapshot.metadata.name,
            snapshot.metadata.note,
            snapshot.version.created_at.isoformat(),
            snapshot.version.created_by,
            snapshot.version.restored_from_version,
        ),
    )


def _insert_change(conn, change: PlanningDraftChange) -> None:
    conn.execute(
        """
        INSERT INTO planning_draft_changes (
            change_id, draft_id, change_type, from_version, to_version,
            actor, occurred_at, summary, metadata
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            change.change_id,
            change.draft_id,
            change.change_type.value,
            change.from_version,
            change.to_version,
            change.actor,
            change.occurred_at.isoformat(),
            change.summary,
            json.dumps(
                [item.model_dump(mode="json") for item in change.metadata],
                ensure_ascii=False,
            ),
        ),
    )


class SqlPlanningDraftRepository:
    def get_active(self, scope: PlanningDraftScope) -> PlanningDraft | None:
        with db_session() as conn:
            row = conn.execute(
                """
                SELECT *
                FROM planning_drafts
                WHERE organization_id = ?
                  AND operational_unit_id = ?
                  AND planning_date = ?
                  AND deleted_at IS NULL
                ORDER BY updated_at DESC
                LIMIT 1
                """,
                (
                    scope.organization_id,
                    scope.operational_unit.external_identifier,
                    scope.planning_date.isoformat(),
                ),
            ).fetchone()
        return _draft_from_row(row) if row else None

    def get_by_id(self, draft_id: str) -> PlanningDraft | None:
        with db_session() as conn:
            row = conn.execute(
                "SELECT * FROM planning_drafts WHERE draft_id = ?",
                (draft_id,),
            ).fetchone()
        return _draft_from_row(row) if row else None

    def get_snapshot(
        self,
        draft_id: str,
        version: int,
    ) -> PlanningDraftSnapshot | None:
        with db_session() as conn:
            row = conn.execute(
                """
                SELECT * FROM planning_draft_versions
                WHERE draft_id = ? AND version = ?
                """,
                (draft_id, version),
            ).fetchone()
        return _snapshot_from_row(row) if row else None

    def get_history(
        self,
        draft_id: str,
        *,
        limit: int = 100,
    ) -> PlanningDraftHistory:
        bounded_limit = max(1, min(limit, 100))
        with db_session() as conn:
            change_count = conn.execute(
                """
                SELECT COUNT(*) AS total
                FROM planning_draft_changes
                WHERE draft_id = ?
                """,
                (draft_id,),
            ).fetchone()
            version_count = conn.execute(
                """
                SELECT COUNT(*) AS total
                FROM planning_draft_versions
                WHERE draft_id = ?
                """,
                (draft_id,),
            ).fetchone()
            changes = conn.execute(
                """
                SELECT * FROM planning_draft_changes
                WHERE draft_id = ?
                ORDER BY occurred_at DESC, to_version DESC
                LIMIT ?
                """,
                (draft_id, bounded_limit),
            ).fetchall()
            snapshots = conn.execute(
                """
                SELECT * FROM planning_draft_versions
                WHERE draft_id = ?
                ORDER BY version DESC
                LIMIT ?
                """,
                (draft_id, bounded_limit),
            ).fetchall()
        return PlanningDraftHistory(
            draft_id=draft_id,
            total_changes=int(change_count["total"]),
            total_versions=int(version_count["total"]),
            changes=tuple(_change_from_row(row) for row in changes),
            snapshots=tuple(_snapshot_from_row(row) for row in snapshots),
        )

    def create(
        self,
        draft: PlanningDraft,
        snapshot: PlanningDraftSnapshot,
        change: PlanningDraftChange,
    ) -> None:
        try:
            with db_session() as conn:
                conn.execute(
                    """
                    INSERT INTO planning_drafts (
                        draft_id, organization_id, operational_unit_id,
                        operational_unit_name, planning_date, name, note,
                        state, version, version_created_at,
                        version_created_by, restored_from_version,
                        created_at, updated_at, deleted_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        draft.draft_id,
                        draft.scope.organization_id,
                        draft.scope.operational_unit.external_identifier,
                        draft.scope.operational_unit.name,
                        draft.scope.planning_date.isoformat(),
                        draft.metadata.name,
                        draft.metadata.note,
                        draft.state.value,
                        draft.version.number,
                        draft.version.created_at.isoformat(),
                        draft.version.created_by,
                        draft.version.restored_from_version,
                        draft.created_at.isoformat(),
                        draft.updated_at.isoformat(),
                        None,
                    ),
                )
                _insert_snapshot(conn, snapshot)
                _insert_change(conn, change)
        except sqlite3.IntegrityError as exc:
            raise PlanningDraftAlreadyExistsError(
                "Esiste gia un Draft attivo per questo contesto."
            ) from exc

    def replace(
        self,
        draft: PlanningDraft,
        snapshot: PlanningDraftSnapshot,
        change: PlanningDraftChange,
        *,
        expected_version: int,
    ) -> bool:
        with db_session() as conn:
            updated = conn.execute(
                """
                UPDATE planning_drafts
                SET name = ?, note = ?, state = ?, version = ?,
                    version_created_at = ?, version_created_by = ?,
                    restored_from_version = ?, updated_at = ?, deleted_at = ?
                WHERE draft_id = ?
                  AND version = ?
                  AND deleted_at IS NULL
                RETURNING draft_id
                """,
                (
                    draft.metadata.name,
                    draft.metadata.note,
                    draft.state.value,
                    draft.version.number,
                    draft.version.created_at.isoformat(),
                    draft.version.created_by,
                    draft.version.restored_from_version,
                    draft.updated_at.isoformat(),
                    draft.deleted_at.isoformat() if draft.deleted_at else None,
                    draft.draft_id,
                    expected_version,
                ),
            ).fetchone()
            if updated is None:
                return False
            _insert_snapshot(conn, snapshot)
            _insert_change(conn, change)
        return True
