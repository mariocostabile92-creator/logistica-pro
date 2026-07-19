import json
import sqlite3

from pydantic import ValidationError

from app.core.configuration.models import (
    ConfigurationRevision,
    ConfigurationScope,
    ConfigurationSection,
    ConfigurationVersion,
)
from app.core.database import db_session
from app.utils.date_utils import utc_now_iso


class StoredConfigurationInvalidError(ValueError):
    pass


class ConfigurationStorageUnavailableError(RuntimeError):
    pass


def init_schema() -> None:
    with db_session() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS configuration_versions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                organization_id TEXT NOT NULL,
                operational_unit_id TEXT NOT NULL,
                adapter_id TEXT NOT NULL,
                version INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                valid_from TEXT NOT NULL,
                created_by TEXT NOT NULL,
                note TEXT,
                sections TEXT NOT NULL,
                UNIQUE (
                    organization_id,
                    operational_unit_id,
                    adapter_id,
                    version
                )
            );

            CREATE INDEX IF NOT EXISTS idx_configuration_scope
                ON configuration_versions (
                    organization_id,
                    operational_unit_id,
                    adapter_id,
                    version
                );
            """
        )


def _scope_value(value: str | None) -> str:
    return value or ""


def _scope_from_row(row: sqlite3.Row) -> ConfigurationScope:
    return ConfigurationScope(
        organization_id=row["organization_id"],
        operational_unit_id=row["operational_unit_id"] or None,
        adapter_id=row["adapter_id"] or None,
    )


def _revision_from_row(row: sqlite3.Row) -> ConfigurationRevision:
    try:
        sections = [
            ConfigurationSection.model_validate(item)
            for item in json.loads(row["sections"])
        ]
    except (json.JSONDecodeError, TypeError, ValidationError) as exc:
        raise StoredConfigurationInvalidError(
            "Configurazione persistita non valida."
        ) from exc
    return ConfigurationRevision(
        scope=_scope_from_row(row),
        version=ConfigurationVersion(
            number=row["version"],
            created_at=row["created_at"],
            valid_from=row["valid_from"],
            created_by=row["created_by"],
            note=row["note"],
        ),
        sections=sections,
    )


def get_latest_revision(
    scope: ConfigurationScope,
) -> ConfigurationRevision | None:
    try:
        with db_session() as conn:
            row = conn.execute(
                """
                SELECT *
                FROM configuration_versions
                WHERE organization_id = ?
                  AND operational_unit_id = ?
                  AND adapter_id = ?
                ORDER BY version DESC
                LIMIT 1
                """,
                (
                    scope.organization_id,
                    _scope_value(scope.operational_unit_id),
                    _scope_value(scope.adapter_id),
                ),
            ).fetchone()
    except sqlite3.OperationalError as exc:
        raise ConfigurationStorageUnavailableError(
            "Configuration storage non disponibile."
        ) from exc
    return _revision_from_row(row) if row else None


def list_revisions(
    scope: ConfigurationScope,
) -> list[ConfigurationRevision]:
    try:
        with db_session() as conn:
            rows = conn.execute(
                """
                SELECT *
                FROM configuration_versions
                WHERE organization_id = ?
                  AND operational_unit_id = ?
                  AND adapter_id = ?
                ORDER BY version DESC
                """,
                (
                    scope.organization_id,
                    _scope_value(scope.operational_unit_id),
                    _scope_value(scope.adapter_id),
                ),
            ).fetchall()
    except sqlite3.OperationalError as exc:
        raise ConfigurationStorageUnavailableError(
            "Configuration storage non disponibile."
        ) from exc
    return [_revision_from_row(row) for row in rows]


def save_revision(
    scope: ConfigurationScope,
    sections: list[ConfigurationSection],
    created_by: str,
    note: str | None = None,
    valid_from: str | None = None,
) -> ConfigurationRevision:
    now = utc_now_iso()
    with db_session() as conn:
        current = conn.execute(
            """
            SELECT COALESCE(MAX(version), 0)
            FROM configuration_versions
            WHERE organization_id = ?
              AND operational_unit_id = ?
              AND adapter_id = ?
            """,
            (
                scope.organization_id,
                _scope_value(scope.operational_unit_id),
                _scope_value(scope.adapter_id),
            ),
        ).fetchone()[0]
        version_number = int(current) + 1
        conn.execute(
            """
            INSERT INTO configuration_versions (
                organization_id, operational_unit_id, adapter_id,
                version, created_at, valid_from, created_by, note,
                sections
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                scope.organization_id,
                _scope_value(scope.operational_unit_id),
                _scope_value(scope.adapter_id),
                version_number,
                now,
                valid_from or now,
                created_by,
                note,
                json.dumps(
                    [
                        section.model_dump(mode="json")
                        for section in sections
                    ],
                    ensure_ascii=False,
                ),
            ),
        )
    return ConfigurationRevision(
        scope=scope,
        version=ConfigurationVersion(
            number=version_number,
            created_at=now,
            valid_from=valid_from or now,
            created_by=created_by,
            note=note,
        ),
        sections=sections,
    )
