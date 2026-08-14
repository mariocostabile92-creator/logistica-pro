import json
import sqlite3
from collections import defaultdict

from app.auth.tenant_context import current_organization_id
from app.core.config import SETTINGS
from app.core.database import db_session
from app.plugins.fleet.domain.errors import AssetIdentifierConflictError
from app.plugins.fleet.domain.models import (
    Asset,
    AssetDocument,
    AssetEvent,
    AssetEventType,
    FleetAssetProfile,
)
from app.utils.date_utils import utc_now_iso


def _ensure_profile_columns(conn, database_backend: str) -> None:
    if database_backend == "postgresql":
        conn.execute(
            """
            ALTER TABLE fleet_asset_profiles
            ADD COLUMN IF NOT EXISTS purchased_on TEXT
            """
        )
        return
    profile_columns = {
        row["name"]
        for row in conn.execute(
            "PRAGMA table_info(fleet_asset_profiles)"
        ).fetchall()
    }
    if "purchased_on" not in profile_columns:
        conn.execute(
            """
            ALTER TABLE fleet_asset_profiles
            ADD COLUMN purchased_on TEXT
            """
        )


def _migrate_sqlite_asset_identity(conn) -> None:
    row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='fleet_assets'"
    ).fetchone()
    definition = str(row["sql"] or "").upper() if row else ""
    if "EXTERNAL_IDENTIFIER TEXT NOT NULL UNIQUE" not in definition:
        return
    conn.execute("PRAGMA foreign_keys = OFF")
    conn.execute("PRAGMA legacy_alter_table = ON")
    conn.executescript(
        """
        ALTER TABLE fleet_assets RENAME TO fleet_assets_global_identity;
        CREATE TABLE fleet_assets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            organization_id TEXT,
            external_identifier TEXT NOT NULL,
            plate TEXT,
            category TEXT,
            status TEXT NOT NULL,
            availability TEXT NOT NULL,
            notes TEXT,
            capabilities TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE (organization_id, external_identifier),
            UNIQUE (organization_id, plate)
        );
        INSERT INTO fleet_assets (
            id, organization_id, external_identifier, plate, category, status,
            availability, notes, capabilities, created_at, updated_at
        )
        SELECT id, organization_id, external_identifier, plate, category, status,
               availability, notes, capabilities, created_at, updated_at
        FROM fleet_assets_global_identity;
        DROP TABLE fleet_assets_global_identity;
        """
    )
    conn.execute("PRAGMA legacy_alter_table = OFF")
    conn.execute("PRAGMA foreign_keys = ON")


def _ensure_asset_tenant_identity(conn, database_backend: str) -> None:
    if database_backend == "postgresql":
        conn.execute(
            "ALTER TABLE fleet_assets DROP CONSTRAINT IF EXISTS "
            "fleet_assets_external_identifier_key"
        )
        conn.execute(
            "ALTER TABLE fleet_assets DROP CONSTRAINT IF EXISTS "
            "fleet_assets_plate_key"
        )
        conn.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_fleet_assets_org_external "
            "ON fleet_assets(organization_id, LOWER(external_identifier))"
        )
        conn.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_fleet_assets_org_plate "
            "ON fleet_assets(organization_id, LOWER(plate)) WHERE plate IS NOT NULL"
        )
        return
    _migrate_sqlite_asset_identity(conn)
    conn.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_fleet_assets_org_external "
        "ON fleet_assets(organization_id, LOWER(external_identifier))"
    )
    conn.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_fleet_assets_org_plate "
        "ON fleet_assets(organization_id, LOWER(plate)) WHERE plate IS NOT NULL"
    )


def _ensure_asset_tenant(conn, database_backend: str) -> None:
    if database_backend == "postgresql":
        conn.execute(
            "ALTER TABLE fleet_assets ADD COLUMN IF NOT EXISTS organization_id TEXT"
        )
    else:
        columns = {
            row["name"]
            for row in conn.execute("PRAGMA table_info(fleet_assets)").fetchall()
        }
        if "organization_id" not in columns:
            conn.execute("ALTER TABLE fleet_assets ADD COLUMN organization_id TEXT")

    if database_backend != "postgresql":
        _ensure_asset_tenant_identity(conn, database_backend)

    owner = conn.execute(
        "SELECT id FROM organizations ORDER BY created_at ASC, id ASC LIMIT 1"
    ).fetchone()
    if owner:
        conn.execute(
            """
            UPDATE fleet_assets
            SET organization_id = ?
            WHERE organization_id IS NULL OR organization_id = 'default'
            """,
            (owner["id"],),
        )
    if database_backend == "postgresql":
        _ensure_asset_tenant_identity(conn, database_backend)
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_fleet_assets_organization "
        "ON fleet_assets(organization_id, external_identifier)"
    )


def init_schema() -> None:
    with db_session() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS fleet_assets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                organization_id TEXT,
                external_identifier TEXT NOT NULL,
                plate TEXT,
                category TEXT,
                status TEXT NOT NULL,
                availability TEXT NOT NULL,
                notes TEXT,
                capabilities TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE (organization_id, external_identifier),
                UNIQUE (organization_id, plate)
            );

            CREATE TABLE IF NOT EXISTS fleet_asset_documents (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                asset_id INTEGER NOT NULL,
                document_type TEXT NOT NULL,
                name TEXT NOT NULL,
                reference TEXT,
                issued_on TEXT,
                expires_on TEXT,
                notes TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY (asset_id) REFERENCES fleet_assets(id)
                    ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS fleet_asset_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                asset_id INTEGER NOT NULL,
                event_type TEXT NOT NULL,
                occurred_at TEXT NOT NULL,
                actor TEXT NOT NULL,
                details TEXT NOT NULL,
                contract_version TEXT NOT NULL,
                FOREIGN KEY (asset_id) REFERENCES fleet_assets(id)
                    ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS fleet_asset_profiles (
                asset_id INTEGER PRIMARY KEY,
                contract_type TEXT NOT NULL,
                company TEXT,
                owner_company TEXT,
                contract_number TEXT,
                monthly_fee TEXT,
                daily_cost TEXT,
                deductible TEXT,
                included_km INTEGER,
                excess_km_cost TEXT,
                starts_on TEXT,
                expires_on TEXT,
                purchased_on TEXT,
                contract_status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (asset_id) REFERENCES fleet_assets(id)
                    ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_fleet_documents_asset
                ON fleet_asset_documents(asset_id);
            CREATE INDEX IF NOT EXISTS idx_fleet_events_asset
                ON fleet_asset_events(asset_id, id);
            """
        )
        _ensure_asset_tenant(conn, SETTINGS.database_backend)
        _ensure_profile_columns(conn, SETTINGS.database_backend)


def _append_event(
    conn: sqlite3.Connection,
    asset_id: int,
    event_type: AssetEventType,
    actor: str,
    details: dict[str, object],
    occurred_at: str,
) -> None:
    conn.execute(
        """
        INSERT INTO fleet_asset_events (
            asset_id, event_type, occurred_at, actor, details,
            contract_version
        )
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            asset_id,
            event_type.value,
            occurred_at,
            actor,
            json.dumps(details, ensure_ascii=False),
            "1.0",
        ),
    )


def _document_from_row(row: sqlite3.Row) -> AssetDocument:
    return AssetDocument(
        id=row["id"],
        asset_id=row["asset_id"],
        document_type=row["document_type"],
        name=row["name"],
        reference=row["reference"],
        issued_on=row["issued_on"],
        expires_on=row["expires_on"],
        notes=row["notes"],
        created_at=row["created_at"],
    )


def _documents_by_asset(
    conn: sqlite3.Connection,
    asset_ids: list[int],
) -> dict[int, list[AssetDocument]]:
    grouped: dict[int, list[AssetDocument]] = defaultdict(list)
    if not asset_ids:
        return grouped
    placeholders = ",".join("?" for _ in asset_ids)
    rows = conn.execute(
        f"""
        SELECT *
        FROM fleet_asset_documents
        WHERE asset_id IN ({placeholders})
        ORDER BY id ASC
        """,
        asset_ids,
    ).fetchall()
    for row in rows:
        grouped[row["asset_id"]].append(_document_from_row(row))
    return grouped


def _profile_from_row(row: sqlite3.Row) -> FleetAssetProfile:
    return FleetAssetProfile(**{key: row[key] for key in row.keys()})


def _profiles_by_asset(
    conn: sqlite3.Connection,
    asset_ids: list[int],
) -> dict[int, FleetAssetProfile]:
    if not asset_ids:
        return {}
    placeholders = ",".join("?" for _ in asset_ids)
    rows = conn.execute(
        f"SELECT * FROM fleet_asset_profiles WHERE asset_id IN ({placeholders})",
        asset_ids,
    ).fetchall()
    return {row["asset_id"]: _profile_from_row(row) for row in rows}


def _operational_status_by_asset(
    conn: sqlite3.Connection,
    asset_ids: list[int],
) -> dict[int, dict[str, object]]:
    if not asset_ids:
        return {}
    placeholders = ",".join("?" for _ in asset_ids)
    rows = conn.execute(
        f"""
        SELECT event.asset_id, event.occurred_at, event.actor, event.details
        FROM fleet_asset_events AS event
        INNER JOIN (
            SELECT asset_id, MAX(id) AS event_id
            FROM fleet_asset_events
            WHERE asset_id IN ({placeholders})
              AND event_type = ?
            GROUP BY asset_id
        ) AS latest ON latest.event_id = event.id
        """,
        [*asset_ids, AssetEventType.OPERATIONAL_STATUS_CHANGED.value],
    ).fetchall()
    result: dict[int, dict[str, object]] = {}
    for row in rows:
        details = json.loads(row["details"])
        result[row["asset_id"]] = {
            "reason": details.get("reason") or details.get("note"),
            "origin": details.get("origin"),
            "actor": row["actor"],
            "updated_at": row["occurred_at"],
            "damage_case_id": details.get("linked_damage_case_id"),
            "damage_case_number": details.get("linked_damage_case_number"),
        }
    return result


def _asset_from_row(
    row: sqlite3.Row,
    documents: list[AssetDocument],
    operational_status: dict[str, object] | None = None,
    profile: FleetAssetProfile | None = None,
) -> Asset:
    operational_status = operational_status or {}
    return Asset(
        id=row["id"],
        external_identifier=row["external_identifier"],
        plate=row["plate"],
        category=row["category"],
        status=row["status"],
        availability=row["availability"],
        operational_status=row["availability"],
        operational_status_reason=operational_status.get("reason"),
        operational_status_origin=operational_status.get("origin"),
        operational_status_actor=operational_status.get("actor"),
        operational_status_updated_at=operational_status.get("updated_at"),
        operational_status_damage_case_id=operational_status.get("damage_case_id"),
        operational_status_damage_case_number=operational_status.get("damage_case_number"),
        notes=row["notes"],
        capabilities=json.loads(row["capabilities"]),
        documents=documents,
        profile=profile,
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _get_asset_in_session(
    conn: sqlite3.Connection,
    asset_id: int,
    organization_id: str | None = None,
) -> Asset | None:
    organization_id = organization_id or current_organization_id()
    row = conn.execute(
        "SELECT * FROM fleet_assets WHERE id = ? AND organization_id = ?",
        (asset_id, organization_id),
    ).fetchone()
    if not row:
        return None
    documents = _documents_by_asset(conn, [asset_id]).get(asset_id, [])
    operational = _operational_status_by_asset(conn, [asset_id]).get(asset_id)
    profile = _profiles_by_asset(conn, [asset_id]).get(asset_id)
    return _asset_from_row(row, documents, operational, profile)


def list_assets() -> list[Asset]:
    organization_id = current_organization_id()
    with db_session() as conn:
        rows = conn.execute(
            """
            SELECT * FROM fleet_assets
            WHERE organization_id = ?
            ORDER BY external_identifier ASC
            """,
            (organization_id,),
        ).fetchall()
        asset_ids = [row["id"] for row in rows]
        documents = _documents_by_asset(conn, asset_ids)
        operational = _operational_status_by_asset(conn, asset_ids)
        profiles = _profiles_by_asset(conn, asset_ids)
        return [
            _asset_from_row(
                row,
                documents.get(row["id"], []),
                operational.get(row["id"]),
                profiles.get(row["id"]),
            )
            for row in rows
        ]


def availability_counts(
    organization_id: str,
) -> tuple[list[dict[str, object]], str | None]:
    """Aggregate canonical Fleet availability in one organization-scoped query."""
    with db_session() as conn:
        rows = conn.execute(
            """
            SELECT availability, COUNT(1) AS count,
                   MAX(updated_at) AS observed_at
            FROM fleet_assets
            WHERE organization_id = ?
            GROUP BY availability
            ORDER BY availability
            """,
            (organization_id,),
        ).fetchall()
    values = [dict(row) for row in rows]
    observed_at = max(
        (str(row["observed_at"]) for row in values if row.get("observed_at")),
        default=None,
    )
    return values, observed_at


def get_asset(asset_id: int) -> Asset | None:
    with db_session() as conn:
        return _get_asset_in_session(conn, asset_id, current_organization_id())


def upsert_profile(
    asset_id: int,
    values: dict[str, object],
    actor: str,
) -> FleetAssetProfile | None:
    now = utc_now_iso()
    organization_id = current_organization_id()
    with db_session() as conn:
        if not conn.execute(
            "SELECT 1 FROM fleet_assets WHERE id = ? AND organization_id = ?",
            (asset_id, organization_id),
        ).fetchone():
            return None
        existing = conn.execute(
            "SELECT created_at FROM fleet_asset_profiles WHERE asset_id = ?",
            (asset_id,),
        ).fetchone()
        created_at = existing["created_at"] if existing else now
        conn.execute(
            """
            INSERT INTO fleet_asset_profiles (
                asset_id, contract_type, company, owner_company,
                contract_number, monthly_fee, daily_cost, deductible,
                included_km, excess_km_cost, starts_on, expires_on,
                purchased_on, contract_status, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(asset_id) DO UPDATE SET
                contract_type = excluded.contract_type,
                company = excluded.company,
                owner_company = excluded.owner_company,
                contract_number = excluded.contract_number,
                monthly_fee = excluded.monthly_fee,
                daily_cost = excluded.daily_cost,
                deductible = excluded.deductible,
                included_km = excluded.included_km,
                excess_km_cost = excluded.excess_km_cost,
                starts_on = excluded.starts_on,
                expires_on = excluded.expires_on,
                purchased_on = excluded.purchased_on,
                contract_status = excluded.contract_status,
                updated_at = excluded.updated_at
            """,
            (
                asset_id, values["contract_type"], values.get("company"),
                values.get("owner_company"), values.get("contract_number"),
                values.get("monthly_fee"), values.get("daily_cost"),
                values.get("deductible"), values.get("included_km"),
                values.get("excess_km_cost"), values.get("starts_on"),
                values.get("expires_on"), values.get("purchased_on"),
                values["contract_status"],
                created_at, now,
            ),
        )
        _append_event(
            conn,
            asset_id,
            AssetEventType.ASSET_UPDATED,
            actor,
            {"profile": {"contract_type": values["contract_type"]}},
            now,
        )
        row = conn.execute(
            "SELECT * FROM fleet_asset_profiles WHERE asset_id = ?",
            (asset_id,),
        ).fetchone()
    return _profile_from_row(row)


def create_asset(values: dict[str, object], actor: str) -> Asset:
    now = utc_now_iso()
    organization_id = current_organization_id()
    try:
        with db_session() as conn:
            cursor = conn.execute(
                """
                INSERT INTO fleet_assets (
                    organization_id, external_identifier, plate, category, status,
                    availability, notes, capabilities, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    organization_id,
                    values["external_identifier"],
                    values.get("plate"),
                    values.get("category"),
                    values["status"],
                    values["availability"],
                    values.get("notes"),
                    json.dumps(values["capabilities"], ensure_ascii=False),
                    now,
                    now,
                ),
            )
            asset_id = int(cursor.lastrowid)
            _append_event(
                conn,
                asset_id,
                AssetEventType.ASSET_CREATED,
                actor,
                {
                    "external_identifier": values["external_identifier"],
                    "status": values["status"],
                    "availability": values["availability"],
                },
                now,
            )
            asset = _get_asset_in_session(conn, asset_id, organization_id)
    except sqlite3.IntegrityError as exc:
        raise AssetIdentifierConflictError(
            "External identifier o targa già associati a un Asset."
        ) from exc
    assert asset is not None
    return asset


def update_asset(
    asset_id: int,
    changes: dict[str, object],
    actor: str,
) -> Asset | None:
    organization_id = current_organization_id()
    try:
        with db_session() as conn:
            current = _get_asset_in_session(conn, asset_id, organization_id)
            if not current:
                return None
            current_values = current.model_dump(
                exclude={"id", "documents", "created_at", "updated_at"}
            )
            next_values = {**current_values, **changes}
            effective_changes = {
                field: {
                    "before": current_values[field],
                    "after": next_values[field],
                }
                for field in changes
                if current_values[field] != next_values[field]
            }
            if not effective_changes:
                return current
            now = utc_now_iso()
            conn.execute(
                """
                UPDATE fleet_assets
                SET plate = ?, category = ?, status = ?, notes = ?,
                    capabilities = ?, updated_at = ?
                WHERE id = ? AND organization_id = ?
                """,
                (
                    next_values["plate"],
                    next_values["category"],
                    next_values["status"],
                    next_values["notes"],
                    json.dumps(next_values["capabilities"], ensure_ascii=False),
                    now,
                    asset_id,
                    organization_id,
                ),
            )
            _append_event(
                conn,
                asset_id,
                AssetEventType.ASSET_UPDATED,
                actor,
                {"changes": effective_changes},
                now,
            )
            return _get_asset_in_session(conn, asset_id, organization_id)
    except sqlite3.IntegrityError as exc:
        raise AssetIdentifierConflictError(
            "La targa è già associata a un altro Asset."
        ) from exc


def observe_availability(
    asset_id: int,
    availability: str,
    note: str | None,
    actor: str,
    event_type: AssetEventType,
    extra_details: dict[str, object] | None = None,
) -> Asset | None:
    organization_id = current_organization_id()
    with db_session() as conn:
        current = _get_asset_in_session(conn, asset_id, organization_id)
        if not current:
            return None
        now = utc_now_iso()
        conn.execute(
            """
            UPDATE fleet_assets
            SET availability = ?, updated_at = ?
            WHERE id = ? AND organization_id = ?
            """,
            (availability, now, asset_id, organization_id),
        )
        details: dict[str, object] = {
            "previous": current.availability,
            "current": availability,
        }
        if note:
            details["note"] = note
        if extra_details:
            details.update(extra_details)
        _append_event(
            conn,
            asset_id,
            event_type,
            actor,
            details,
            now,
        )
        return _get_asset_in_session(conn, asset_id, organization_id)


def add_document(
    asset_id: int,
    values: dict[str, object],
    actor: str,
) -> AssetDocument | None:
    organization_id = current_organization_id()
    with db_session() as conn:
        if not _get_asset_in_session(conn, asset_id, organization_id):
            return None
        now = utc_now_iso()
        cursor = conn.execute(
            """
            INSERT INTO fleet_asset_documents (
                asset_id, document_type, name, reference, issued_on,
                expires_on, notes, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                asset_id,
                values["document_type"],
                values["name"],
                values.get("reference"),
                values.get("issued_on"),
                values.get("expires_on"),
                values.get("notes"),
                now,
            ),
        )
        document_id = int(cursor.lastrowid)
        _append_event(
            conn,
            asset_id,
            AssetEventType.ASSET_DOCUMENT_ADDED,
            actor,
            {
                "document_id": document_id,
                "document_type": values["document_type"],
                "name": values["name"],
            },
            now,
        )
        row = conn.execute(
            "SELECT * FROM fleet_asset_documents WHERE id = ?",
            (document_id,),
        ).fetchone()
        return _document_from_row(row)


def list_events(asset_id: int) -> list[AssetEvent]:
    organization_id = current_organization_id()
    with db_session() as conn:
        if not _get_asset_in_session(conn, asset_id, organization_id):
            return []
        rows = conn.execute(
            """
            SELECT *
            FROM fleet_asset_events
            WHERE asset_id = ?
            ORDER BY occurred_at ASC, id ASC
            """,
            (asset_id,),
        ).fetchall()
    return [
        AssetEvent(
            id=row["id"],
            asset_id=row["asset_id"],
            event_type=row["event_type"],
            occurred_at=row["occurred_at"],
            actor=row["actor"],
            details=json.loads(row["details"]),
            contract_version=row["contract_version"],
        )
        for row in rows
    ]
