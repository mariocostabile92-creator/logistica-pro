import re

from app.core.config import SETTINGS


_SQL_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def ensure_column(conn, table: str, column: str, definition: str) -> None:
    if SETTINGS.database_backend == "postgresql":
        conn.execute(
            f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {column} {definition}"
        )
        return
    existing = {
        row["name"]
        for row in conn.execute(f"PRAGMA table_info({table})").fetchall()
    }
    if column not in existing:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def ensure_postgresql_bigint(conn, table: str, column: str) -> None:
    """Widen one existing PostgreSQL integer column without touching SQLite."""
    if SETTINGS.database_backend != "postgresql":
        return
    if not _SQL_IDENTIFIER.fullmatch(table) or not _SQL_IDENTIFIER.fullmatch(column):
        raise ValueError("Invalid SQL identifier for BIGINT migration.")
    row = conn.execute(
        """
        SELECT data_type
        FROM information_schema.columns
        WHERE table_schema = current_schema()
          AND table_name = ? AND column_name = ?
        """,
        (table, column),
    ).fetchone()
    if row and row["data_type"] != "bigint":
        conn.execute(
            f"ALTER TABLE {table} ALTER COLUMN {column} "
            f"TYPE BIGINT USING {column}::BIGINT"
        )
