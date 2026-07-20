import json
import sqlite3

from app.briefing.models import DailyOperationsBriefing
from app.core.database import db_session


def init_schema() -> None:
    with db_session() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS daily_briefings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                briefing_id TEXT NOT NULL UNIQUE,
                fingerprint TEXT NOT NULL UNIQUE,
                planning_id INTEGER NOT NULL,
                planning_version INTEGER NOT NULL,
                configuration_version INTEGER NOT NULL,
                contract_version TEXT NOT NULL,
                briefing_revision INTEGER NOT NULL,
                generated_at TEXT NOT NULL,
                payload TEXT NOT NULL,
                is_demo INTEGER NOT NULL DEFAULT 0,
                FOREIGN KEY (planning_id) REFERENCES plannings(id)
                    ON DELETE CASCADE,
                UNIQUE (planning_id, briefing_revision)
            );

            CREATE INDEX IF NOT EXISTS idx_daily_briefings_planning
                ON daily_briefings(planning_id, briefing_revision);
            """
        )


def _from_row(row) -> DailyOperationsBriefing | None:
    if not row:
        return None
    return DailyOperationsBriefing.model_validate(
        json.loads(row["payload"])
    )


def get_by_fingerprint(
    fingerprint: str,
) -> DailyOperationsBriefing | None:
    with db_session() as conn:
        row = conn.execute(
            """
            SELECT payload
            FROM daily_briefings
            WHERE fingerprint = ?
            """,
            (fingerprint,),
        ).fetchone()
    return _from_row(row)


def next_revision(planning_id: int) -> int:
    with db_session() as conn:
        row = conn.execute(
            """
            SELECT COALESCE(MAX(briefing_revision), 0) AS current_revision
            FROM daily_briefings
            WHERE planning_id = ?
            """,
            (planning_id,),
        ).fetchone()
    return int(row["current_revision"]) + 1


def save(
    briefing: DailyOperationsBriefing,
) -> DailyOperationsBriefing:
    payload = json.dumps(
        briefing.model_dump(mode="json"),
        ensure_ascii=False,
        separators=(",", ":"),
    )
    try:
        with db_session() as conn:
            conn.execute(
                """
                INSERT INTO daily_briefings (
                    briefing_id, fingerprint, planning_id,
                    planning_version, configuration_version,
                    contract_version, briefing_revision, generated_at,
                    payload, is_demo
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    briefing.briefing_id,
                    briefing.fingerprint,
                    briefing.planning_id,
                    briefing.planning_version,
                    briefing.configuration_version,
                    briefing.contract_version,
                    briefing.briefing_revision,
                    briefing.generated_at,
                    payload,
                    int(briefing.is_demo),
                ),
            )
    except sqlite3.IntegrityError:
        existing = get_by_fingerprint(str(briefing.fingerprint))
        if existing:
            return existing
        raise
    return briefing
