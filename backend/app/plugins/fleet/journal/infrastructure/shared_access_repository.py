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
            CREATE UNIQUE INDEX IF NOT EXISTS idx_journal_shared_access_active
                ON journal_shared_access(status) WHERE status = 'active';
            """
        )


def _dict(row) -> dict | None:
    return {key: row[key] for key in row.keys()} if row else None


def active() -> dict | None:
    with db_session() as conn:
        row = conn.execute(
            """
            SELECT id, token, status, created_at, revoked_at, last_used_at
            FROM journal_shared_access
            WHERE status = 'active'
            ORDER BY created_at DESC
            LIMIT 1
            """
        ).fetchone()
    return _dict(row)


def get_by_token(token: str) -> dict | None:
    with db_session() as conn:
        row = conn.execute(
            """
            SELECT id, token, status, created_at, revoked_at, last_used_at
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
                id, token, status, created_at, revoked_at, last_used_at
            ) VALUES (?, ?, 'active', ?, NULL, NULL)
            """,
            (values["id"], values["token"], values["created_at"]),
        )
    return active()  # type: ignore[return-value]


def revoke(access_id: str, revoked_at: str) -> dict | None:
    with db_session() as conn:
        conn.execute(
            """
            UPDATE journal_shared_access
            SET status = 'revoked', revoked_at = ?
            WHERE id = ? AND status = 'active'
            """,
            (revoked_at, access_id),
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

