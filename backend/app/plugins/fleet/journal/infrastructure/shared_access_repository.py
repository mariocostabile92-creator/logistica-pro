from app.core.config import SETTINGS
from app.core.database import db_session


def init_schema() -> None:
    with db_session() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS journal_shared_access (
                id TEXT PRIMARY KEY,
                token TEXT NOT NULL UNIQUE,
                status TEXT NOT NULL DEFAULT 'active',
                created_at TEXT NOT NULL,
                revoked_at TEXT,
                last_used_at TEXT
            );
            """
        )
        _ensure_column(conn, "organization_id", "TEXT")
        _ensure_column(conn, "expires_at", "TEXT")
        owner = conn.execute(
            "SELECT id FROM organizations ORDER BY created_at ASC, id ASC LIMIT 1"
        ).fetchone()
        if owner:
            conn.execute(
                """
                UPDATE journal_shared_access SET organization_id=?
                WHERE organization_id IS NULL OR organization_id='default'
                """,
                (owner["id"],),
            )
        conn.execute("DROP INDEX IF EXISTS idx_journal_shared_access_active")
        conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_journal_shared_access_active_org ON journal_shared_access(organization_id) WHERE status = 'active'")


def _ensure_column(conn, name: str, definition: str) -> None:
    if SETTINGS.database_backend == "postgresql":
        conn.execute(f"ALTER TABLE journal_shared_access ADD COLUMN IF NOT EXISTS {name} {definition}")
    else:
        columns = {row["name"] for row in conn.execute("PRAGMA table_info(journal_shared_access)").fetchall()}
        if name not in columns:
            conn.execute(f"ALTER TABLE journal_shared_access ADD COLUMN {name} {definition}")


def _dict(row) -> dict | None:
    return {key: row[key] for key in row.keys()} if row else None


def active(organization_id: str) -> dict | None:
    with db_session() as conn:
        row = conn.execute(
            """
            SELECT id, token, status, created_at, revoked_at, last_used_at, organization_id, expires_at
            FROM journal_shared_access
            WHERE status = 'active' AND organization_id = ?
            ORDER BY created_at DESC
            LIMIT 1
            """
            , (organization_id,)).fetchone()
    return _dict(row)


def get_by_token(token: str) -> dict | None:
    with db_session() as conn:
        row = conn.execute(
            """
            SELECT id, token, status, created_at, revoked_at, last_used_at, organization_id, expires_at
            FROM journal_shared_access
            WHERE token = ?
            """,
            (token,),
        ).fetchone()
    return _dict(row)


def create(values: dict) -> dict:
    with db_session() as conn:
        conn.execute(
            """
            INSERT INTO journal_shared_access (
                id, token, status, created_at, revoked_at, last_used_at, organization_id, expires_at
            ) VALUES (?, ?, 'active', ?, NULL, NULL, ?, ?)
            """,
            (values["id"], values["token"], values["created_at"], values["organization_id"], values.get("expires_at")),
        )
    return active(str(values["organization_id"]))  # type: ignore[return-value]


def revoke(access_id: str, revoked_at: str, organization_id: str | None = None) -> dict | None:
    with db_session() as conn:
        conn.execute(
            """
            UPDATE journal_shared_access
            SET status = 'revoked', revoked_at = ?
            WHERE id = ? AND status = 'active' AND (? IS NULL OR organization_id = ?)
            """,
            (revoked_at, access_id, organization_id, organization_id),
        )
        row = conn.execute(
            """
            SELECT id, token, status, created_at, revoked_at, last_used_at
            FROM journal_shared_access WHERE id = ?
            """,
            (access_id,),
        ).fetchone()
    return _dict(row)


def touch(token: str, used_at: str) -> dict | None:
    with db_session() as conn:
        conn.execute(
            """
            UPDATE journal_shared_access
            SET last_used_at = ?
            WHERE token = ? AND status = 'active'
            """,
            (used_at, token),
        )
    return get_by_token(token)
