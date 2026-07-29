import re
import sqlite3
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from typing import Any

from app.core.config import SETTINGS, ensure_data_dir


_IDENTITY_TABLES = {
    "analyses",
    "assignments",
    "configuration_versions",
    "fleet_asset_documents",
    "fleet_asset_events",
    "fleet_assets",
    "journal_sessions",
    "imports",
    "operation_snapshots",
    "planning_events",
    "planning_versions",
    "plannings",
}


class DatabaseRow:
    def __init__(self, columns: Sequence[str], values: Sequence[Any]) -> None:
        self._columns = tuple(columns)
        self._values = tuple(values)
        self._positions = {
            column: position
            for position, column in enumerate(self._columns)
        }

    def __getitem__(self, key: int | str) -> Any:
        if isinstance(key, int):
            return self._values[key]
        return self._values[self._positions[key]]

    def keys(self) -> tuple[str, ...]:
        return self._columns


class PostgresCursor:
    def __init__(self, cursor: Any, lastrowid: int | None = None) -> None:
        self._cursor = cursor
        self.lastrowid = lastrowid

    def _columns(self) -> tuple[str, ...]:
        if not self._cursor.description:
            return ()
        return tuple(
            item.name if hasattr(item, "name") else item[0]
            for item in self._cursor.description
        )

    def fetchone(self) -> DatabaseRow | None:
        row = self._cursor.fetchone()
        if row is None:
            return None
        return DatabaseRow(self._columns(), row)

    def fetchall(self) -> list[DatabaseRow]:
        columns = self._columns()
        return [DatabaseRow(columns, row) for row in self._cursor.fetchall()]


def _postgres_statement(statement: str) -> tuple[str, bool]:
    translated = statement.replace("?", "%s")
    insert = re.match(
        r"\s*INSERT\s+INTO\s+([a-zA-Z_][a-zA-Z0-9_]*)",
        translated,
        flags=re.IGNORECASE,
    )
    returns_identity = bool(
        insert
        and insert.group(1).casefold() in _IDENTITY_TABLES
        and not re.search(r"\bRETURNING\b", translated, flags=re.IGNORECASE)
    )
    if returns_identity:
        translated = translated.rstrip().rstrip(";") + " RETURNING id"
    return translated, returns_identity


def _postgres_schema_statement(statement: str) -> str:
    return re.sub(
        r"\bINTEGER\s+PRIMARY\s+KEY\s+AUTOINCREMENT\b",
        "SERIAL PRIMARY KEY",
        statement,
        flags=re.IGNORECASE,
    )


class PostgresConnection:
    def __init__(self, connection: Any) -> None:
        self._connection = connection

    def execute(
        self,
        statement: str,
        parameters: Sequence[Any] | None = None,
    ) -> PostgresCursor:
        translated, returns_identity = _postgres_statement(statement)
        try:
            cursor = self._connection.cursor()
            cursor.execute(translated, parameters or ())
            lastrowid = None
            if returns_identity:
                inserted = cursor.fetchone()
                lastrowid = int(inserted[0]) if inserted else None
            return PostgresCursor(cursor, lastrowid)
        except Exception as exc:
            _raise_compatible_database_error(exc)
            raise

    def executescript(self, script: str) -> None:
        for statement in script.split(";"):
            if statement.strip():
                self.execute(_postgres_schema_statement(statement))

    def commit(self) -> None:
        self._connection.commit()

    def rollback(self) -> None:
        self._connection.rollback()

    def close(self) -> None:
        self._connection.close()


def _raise_compatible_database_error(exc: Exception) -> None:
    try:
        import psycopg
    except ImportError:
        raise exc
    if isinstance(exc, psycopg.IntegrityError):
        raise sqlite3.IntegrityError(str(exc)) from exc
    if isinstance(exc, (psycopg.OperationalError, psycopg.InterfaceError)):
        raise sqlite3.OperationalError(str(exc)) from exc
    if isinstance(exc, psycopg.Error):
        raise sqlite3.DatabaseError(str(exc)) from exc


def _normalize_postgres_url(url: str | None) -> str | None:
    if not url:
        return None
    if url.startswith("postgres://"):
        return "postgresql://" + url.removeprefix("postgres://")
    if url.startswith("postgresql+psycopg://"):
        return "postgresql://" + url.removeprefix("postgresql+psycopg://")
    if url.startswith("postgresql://"):
        return url
    if url.startswith("sqlite://"):
        return None
    raise ValueError("DATABASE_URL deve usare PostgreSQL o SQLite.")


def _postgres_url() -> str | None:
    return _normalize_postgres_url(SETTINGS.database_url)


def _sqlite_path() -> str:
    url = SETTINGS.database_url
    if not url or not url.startswith("sqlite://"):
        return str(SETTINGS.database_path)
    path = url.removeprefix("sqlite:///")
    return path or str(SETTINGS.database_path)


def get_connection() -> sqlite3.Connection | PostgresConnection:
    postgres_url = _postgres_url()
    if postgres_url:
        try:
            import psycopg
        except ImportError as exc:
            raise RuntimeError(
                "Il driver PostgreSQL psycopg non e installato."
            ) from exc
        return PostgresConnection(
            psycopg.connect(postgres_url, connect_timeout=10)
        )

    ensure_data_dir()
    conn = sqlite3.connect(_sqlite_path())
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


@contextmanager
def db_session() -> Iterator[sqlite3.Connection | PostgresConnection]:
    conn = get_connection()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def database_is_ready() -> bool:
    try:
        with db_session() as conn:
            row = conn.execute("SELECT 1").fetchone()
        return bool(row and row[0] == 1)
    except Exception:
        return False


def init_db() -> None:
    with db_session() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS imports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                dataset_type TEXT NOT NULL,
                original_filename TEXT NOT NULL,
                imported_at TEXT NOT NULL,
                sheet_name TEXT,
                column_mapping TEXT NOT NULL,
                normalized_rows TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS analyses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                summary TEXT NOT NULL,
                conflicts TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS operation_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                planning_import_id INTEGER NOT NULL,
                fleet_import_id INTEGER NOT NULL,
                reserve_threshold INTEGER NOT NULL,
                payload TEXT NOT NULL,
                FOREIGN KEY (planning_import_id) REFERENCES imports(id),
                FOREIGN KEY (fleet_import_id) REFERENCES imports(id)
            );

            CREATE TABLE IF NOT EXISTS plannings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                operation_date TEXT NOT NULL,
                station TEXT,
                source_planning_import_id INTEGER NOT NULL,
                source_fleet_import_id INTEGER NOT NULL,
                status TEXT NOT NULL,
                version INTEGER NOT NULL,
                reserve_threshold INTEGER NOT NULL,
                configuration TEXT NOT NULL,
                summary TEXT NOT NULL,
                conflicts TEXT NOT NULL,
                generation_metadata TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (source_planning_import_id) REFERENCES imports(id),
                FOREIGN KEY (source_fleet_import_id) REFERENCES imports(id)
            );

            CREATE TABLE IF NOT EXISTS assignments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                planning_id INTEGER NOT NULL,
                operation_date TEXT NOT NULL,
                station TEXT NOT NULL,
                route_id TEXT NOT NULL,
                cycle_or_wave TEXT,
                driver_id TEXT,
                driver_name TEXT,
                vehicle_id TEXT,
                plate TEXT,
                assignment_status TEXT NOT NULL,
                assignment_source TEXT NOT NULL,
                confidence REAL NOT NULL,
                reasons TEXT NOT NULL,
                data_used TEXT NOT NULL,
                warnings TEXT NOT NULL,
                alternatives TEXT NOT NULL,
                manual_override INTEGER NOT NULL DEFAULT 0,
                confirmed INTEGER NOT NULL DEFAULT 0,
                notes TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (planning_id) REFERENCES plannings(id) ON DELETE CASCADE,
                UNIQUE (planning_id, route_id)
            );

            CREATE TABLE IF NOT EXISTS planning_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                planning_id INTEGER NOT NULL,
                event_type TEXT NOT NULL,
                entity_type TEXT NOT NULL,
                entity_id TEXT NOT NULL,
                reason TEXT NOT NULL,
                simulated INTEGER NOT NULL,
                applied INTEGER NOT NULL,
                impact_summary TEXT NOT NULL,
                payload TEXT NOT NULL,
                diff TEXT NOT NULL,
                actor TEXT NOT NULL,
                created_at TEXT NOT NULL,
                applied_at TEXT,
                FOREIGN KEY (planning_id) REFERENCES plannings(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS planning_versions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                planning_id INTEGER NOT NULL,
                version INTEGER NOT NULL,
                change_type TEXT NOT NULL,
                change_payload TEXT NOT NULL,
                actor TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (planning_id) REFERENCES plannings(id) ON DELETE CASCADE,
                UNIQUE (planning_id, version)
            );

            CREATE INDEX IF NOT EXISTS idx_assignments_planning
                ON assignments(planning_id);
            CREATE INDEX IF NOT EXISTS idx_events_planning
                ON planning_events(planning_id);
            CREATE INDEX IF NOT EXISTS idx_versions_planning
                ON planning_versions(planning_id);
            """
        )
