from collections.abc import Sequence

from app.core.database import db_session
from app.plugins.workforce.domain.driver_shift_planning import (
    DriverShiftPlanning,
    DriverShiftPlanningError,
    DriverShiftPlanningNotFoundError,
    DriverShiftPlanningSource,
    DriverShiftPlanningSourceNotFoundError,
    DriverShiftPlanningStatus,
)
from app.utils.date_utils import utc_now_iso


def _planning(row) -> DriverShiftPlanning:
    return DriverShiftPlanning.model_validate({key: row[key] for key in row.keys()})


def _source(row) -> DriverShiftPlanningSource:
    date_from = row["date_from"]
    date_to = row["date_to"]
    period_start = row["period_start"]
    period_end = row["period_end"]
    warnings: list[str] = []
    if row["status"] == "UNAVAILABLE_FOR_MERGE":
        compatibility = "UNAVAILABLE"
        warnings.append("La source non dispone di righe immutabili per il merge.")
    elif date_from < period_start or date_to > period_end:
        compatibility = "PARTIAL_OVERLAP"
        warnings.append("La source copre solo parzialmente il periodo del planning.")
    else:
        compatibility = "COMPATIBLE"
    return DriverShiftPlanningSource.model_validate({
        "id": row["id"],
        "organization_id": row["organization_id"],
        "driver_shift_planning_id": row["driver_shift_planning_id"],
        "workforce_import_id": row["workforce_import_id"],
        "source_filename": row["source_filename"],
        "imported_at": row["imported_at"],
        "row_count": int(row["row_count"] or 0),
        "source_order": row["source_order"],
        "added_at": row["added_at"],
        "added_by": row["added_by"],
        "status": row["status"],
        "date_from": date_from,
        "date_to": date_to,
        "period_compatibility": compatibility,
        "warnings": warnings,
    })


def create_planning(
    organization_id: str,
    period_start: str,
    period_end: str,
    label: str | None,
    actor: str,
) -> DriverShiftPlanning:
    now = utc_now_iso()
    with db_session() as conn:
        cursor = conn.execute(
            """
            INSERT INTO driver_shift_plannings (
                organization_id, label, period_start, period_end, status,
                version, created_at, created_by, updated_at
            ) VALUES (?, ?, ?, ?, 'DRAFT', 1, ?, ?, ?)
            """,
            (organization_id, label, period_start, period_end, now, actor, now),
        )
        row = conn.execute(
            "SELECT * FROM driver_shift_plannings WHERE id = ? AND organization_id = ?",
            (cursor.lastrowid, organization_id),
        ).fetchone()
    assert row is not None
    return _planning(row)


def get_planning(organization_id: str, planning_id: int) -> DriverShiftPlanning:
    with db_session() as conn:
        row = conn.execute(
            "SELECT * FROM driver_shift_plannings WHERE id = ? AND organization_id = ?",
            (planning_id, organization_id),
        ).fetchone()
    if row is None:
        raise DriverShiftPlanningNotFoundError("Logical planning non trovato.")
    return _planning(row)


def list_plannings(organization_id: str) -> list[DriverShiftPlanning]:
    with db_session() as conn:
        rows = conn.execute(
            """
            SELECT * FROM driver_shift_plannings
            WHERE organization_id = ?
            ORDER BY
                CASE status
                    WHEN 'DRAFT' THEN 0
                    WHEN 'ACTIVE' THEN 1
                    ELSE 2
                END,
                updated_at DESC,
                id DESC
            """,
            (organization_id,),
        ).fetchall()
    return [_planning(row) for row in rows]


def source_facts(organization_id: str, workforce_import_id: int) -> dict[str, object] | None:
    with db_session() as conn:
        row = conn.execute(
            """
            SELECT i.id, i.original_filename,
                   COUNT(r.id) AS source_row_count,
                   MIN(r.operational_date) AS date_from,
                   MAX(r.operational_date) AS date_to
            FROM workforce_imports i
            LEFT JOIN workforce_import_rows r
              ON r.workforce_import_id = i.id
             AND r.organization_id = i.organization_id
             AND r.row_kind = 'shift'
             AND r.operational_date IS NOT NULL
            WHERE i.id = ? AND i.organization_id = ?
            GROUP BY i.id, i.original_filename
            """,
            (workforce_import_id, organization_id),
        ).fetchone()
    return ({key: row[key] for key in row.keys()} if row else None)


def import_reference_by_fingerprint(
    organization_id: str,
    fingerprint: str,
) -> dict[str, object] | None:
    with db_session() as conn:
        row = conn.execute(
            """
            SELECT id AS workforce_import_id, fingerprint,
                   original_filename, imported_at
            FROM workforce_imports
            WHERE organization_id = ? AND fingerprint = ?
            """,
            (organization_id, fingerprint),
        ).fetchone()
    return ({key: row[key] for key in row.keys()} if row else None)


def list_sources(
    organization_id: str,
    planning_id: int,
) -> list[DriverShiftPlanningSource]:
    get_planning(organization_id, planning_id)
    with db_session() as conn:
        rows = conn.execute(
            """
            SELECT s.*, i.original_filename AS source_filename,
                   i.imported_at,
                   COUNT(r.id) AS row_count,
                   MIN(r.operational_date) AS date_from,
                   MAX(r.operational_date) AS date_to,
                   p.period_start, p.period_end
            FROM driver_shift_planning_sources s
            JOIN driver_shift_plannings p
              ON p.id = s.driver_shift_planning_id
             AND p.organization_id = s.organization_id
            JOIN workforce_imports i
              ON i.id = s.workforce_import_id
             AND i.organization_id = s.organization_id
            LEFT JOIN workforce_import_rows r
              ON r.workforce_import_id = s.workforce_import_id
             AND r.organization_id = s.organization_id
             AND r.row_kind = 'shift'
             AND r.operational_date IS NOT NULL
            WHERE s.organization_id = ?
              AND s.driver_shift_planning_id = ?
            GROUP BY s.id, s.organization_id, s.driver_shift_planning_id,
                     s.workforce_import_id, s.source_order, s.added_at,
                     s.added_by, s.status, i.original_filename, i.imported_at,
                     p.period_start, p.period_end
            ORDER BY s.source_order, s.id
            """,
            (organization_id, planning_id),
        ).fetchall()
    return [_source(row) for row in rows]


def add_source_record(
    organization_id: str,
    planning_id: int,
    workforce_import_id: int,
    source_order: int,
    status: str,
    actor: str,
) -> int:
    now = utc_now_iso()
    with db_session() as conn:
        planning = conn.execute(
            "SELECT status FROM driver_shift_plannings WHERE id = ? AND organization_id = ?",
            (planning_id, organization_id),
        ).fetchone()
        if planning is None:
            raise DriverShiftPlanningNotFoundError("Logical planning non trovato.")
        if planning["status"] != DriverShiftPlanningStatus.DRAFT.value:
            raise DriverShiftPlanningError(
                "Le source possono essere modificate solo in DRAFT."
            )
        existing = conn.execute(
            """
            SELECT id FROM driver_shift_planning_sources
            WHERE organization_id = ? AND driver_shift_planning_id = ?
              AND workforce_import_id = ?
            """,
            (organization_id, planning_id, workforce_import_id),
        ).fetchone()
        if existing:
            return int(existing["id"])
        cursor = conn.execute(
            """
            INSERT INTO driver_shift_planning_sources (
                organization_id, driver_shift_planning_id,
                workforce_import_id, source_order, added_at, added_by, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                organization_id, planning_id, workforce_import_id,
                source_order, now, actor, status,
            ),
        )
        conn.execute(
            """
            UPDATE driver_shift_plannings
            SET version = version + 1, updated_at = ?
            WHERE id = ? AND organization_id = ?
            """,
            (now, planning_id, organization_id),
        )
        return int(cursor.lastrowid)


def remove_source_record(
    organization_id: str,
    planning_id: int,
    source_id: int,
) -> None:
    now = utc_now_iso()
    with db_session() as conn:
        planning = conn.execute(
            "SELECT status FROM driver_shift_plannings WHERE id = ? AND organization_id = ?",
            (planning_id, organization_id),
        ).fetchone()
        if planning is None:
            raise DriverShiftPlanningNotFoundError("Logical planning non trovato.")
        if planning["status"] != DriverShiftPlanningStatus.DRAFT.value:
            raise DriverShiftPlanningError(
                "Le source possono essere modificate solo in DRAFT."
            )
        cursor = conn.execute(
            """
            DELETE FROM driver_shift_planning_sources
            WHERE id = ? AND driver_shift_planning_id = ? AND organization_id = ?
            """,
            (source_id, planning_id, organization_id),
        )
        if cursor.rowcount == 0:
            raise DriverShiftPlanningSourceNotFoundError("Source del planning non trovata.")
        conn.execute(
            """
            UPDATE driver_shift_plannings
            SET version = version + 1, updated_at = ?
            WHERE id = ? AND organization_id = ?
            """,
            (now, planning_id, organization_id),
        )


def replace_source_records(
    organization_id: str,
    planning_id: int,
    sources: Sequence[tuple[int, int, str]],
    actor: str,
) -> None:
    now = utc_now_iso()
    with db_session() as conn:
        planning = conn.execute(
            "SELECT status FROM driver_shift_plannings WHERE id = ? AND organization_id = ?",
            (planning_id, organization_id),
        ).fetchone()
        if planning is None:
            raise DriverShiftPlanningNotFoundError("Logical planning non trovato.")
        if planning["status"] != DriverShiftPlanningStatus.DRAFT.value:
            raise DriverShiftPlanningError(
                "Le source possono essere modificate solo in DRAFT."
            )
        conn.execute(
            "DELETE FROM driver_shift_planning_sources WHERE organization_id = ? AND driver_shift_planning_id = ?",
            (organization_id, planning_id),
        )
        conn.executemany(
            """
            INSERT INTO driver_shift_planning_sources (
                organization_id, driver_shift_planning_id,
                workforce_import_id, source_order, added_at, added_by, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (organization_id, planning_id, import_id, order, now, actor, status)
                for import_id, order, status in sources
            ],
        )
        conn.execute(
            """
            UPDATE driver_shift_plannings
            SET version = version + 1, updated_at = ?
            WHERE id = ? AND organization_id = ?
            """,
            (now, planning_id, organization_id),
        )


def merge_rows(organization_id: str, planning_id: int) -> list[dict[str, object]]:
    with db_session() as conn:
        rows = conn.execute(
            """
            SELECT r.*, i.original_filename AS source_filename,
                   s.source_order
            FROM driver_shift_planning_sources s
            JOIN workforce_imports i
              ON i.id = s.workforce_import_id
             AND i.organization_id = s.organization_id
            JOIN workforce_import_rows r
              ON r.workforce_import_id = s.workforce_import_id
             AND r.organization_id = s.organization_id
            WHERE s.organization_id = ?
              AND s.driver_shift_planning_id = ?
              AND s.status = 'AVAILABLE'
              AND r.row_kind = 'shift'
              AND r.operational_date IS NOT NULL
            ORDER BY s.source_order, s.id, r.id
            """,
            (organization_id, planning_id),
        ).fetchall()
    return [{key: row[key] for key in row.keys()} for row in rows]


def list_identity_rows_for_logical_planning(
    organization_id: str,
    planning_id: int,
) -> list[dict[str, object]]:
    get_planning(organization_id, planning_id)
    with db_session() as conn:
        rows = conn.execute(
            """
            SELECT r.*, i.original_filename AS source_filename,
                   s.source_order
            FROM driver_shift_planning_sources s
            JOIN workforce_imports i
              ON i.id = s.workforce_import_id
             AND i.organization_id = s.organization_id
            JOIN workforce_import_rows r
              ON r.workforce_import_id = s.workforce_import_id
             AND r.organization_id = s.organization_id
            WHERE s.organization_id = ?
              AND s.driver_shift_planning_id = ?
              AND r.row_kind = 'identity'
            ORDER BY s.source_order, s.id, r.id
            """,
            (organization_id, planning_id),
        ).fetchall()
    return [{key: row[key] for key in row.keys()} for row in rows]
