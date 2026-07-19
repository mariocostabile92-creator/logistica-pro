import json
from typing import Any

from app.core.database import db_session
from app.utils.date_utils import utc_now_iso


def save_import(
    dataset_type: str,
    original_filename: str,
    sheet_name: str | None,
    column_mapping: list[dict[str, Any]],
    normalized_rows: list[dict[str, Any]],
) -> int:
    with db_session() as conn:
        cursor = conn.execute(
            """
            INSERT INTO imports (
                dataset_type, original_filename, imported_at, sheet_name,
                column_mapping, normalized_rows
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                dataset_type,
                original_filename,
                utc_now_iso(),
                sheet_name,
                json.dumps(column_mapping, ensure_ascii=False),
                json.dumps(normalized_rows, ensure_ascii=False),
            ),
        )
        return int(cursor.lastrowid)


def get_latest_import(dataset_type: str) -> dict[str, Any] | None:
    with db_session() as conn:
        row = conn.execute(
            """
            SELECT *
            FROM imports
            WHERE dataset_type = ?
            ORDER BY id DESC
            LIMIT 1
            """,
            (dataset_type,),
        ).fetchone()
    if row is None:
        return None
    return {
        "id": row["id"],
        "dataset_type": row["dataset_type"],
        "original_filename": row["original_filename"],
        "imported_at": row["imported_at"],
        "sheet_name": row["sheet_name"],
        "column_mapping": json.loads(row["column_mapping"]),
        "normalized_rows": json.loads(row["normalized_rows"]),
    }


def get_import(import_id: int, dataset_type: str | None = None) -> dict[str, Any] | None:
    query = "SELECT * FROM imports WHERE id = ?"
    params: tuple[object, ...] = (import_id,)
    if dataset_type:
        query += " AND dataset_type = ?"
        params = (import_id, dataset_type)
    with db_session() as conn:
        row = conn.execute(query, params).fetchone()
    if row is None:
        return None
    return {
        "id": row["id"],
        "dataset_type": row["dataset_type"],
        "original_filename": row["original_filename"],
        "imported_at": row["imported_at"],
        "sheet_name": row["sheet_name"],
        "column_mapping": json.loads(row["column_mapping"]),
        "normalized_rows": json.loads(row["normalized_rows"]),
    }


def save_analysis(summary: dict[str, Any], conflicts: list[dict[str, Any]]) -> int:
    with db_session() as conn:
        cursor = conn.execute(
            """
            INSERT INTO analyses (created_at, summary, conflicts)
            VALUES (?, ?, ?)
            """,
            (
                utc_now_iso(),
                json.dumps(summary, ensure_ascii=False),
                json.dumps(conflicts, ensure_ascii=False),
            ),
        )
        return int(cursor.lastrowid)


def get_latest_analysis() -> dict[str, Any] | None:
    with db_session() as conn:
        row = conn.execute(
            """
            SELECT *
            FROM analyses
            ORDER BY id DESC
            LIMIT 1
            """
        ).fetchone()
    if row is None:
        return None
    return {
        "id": row["id"],
        "created_at": row["created_at"],
        "summary": json.loads(row["summary"]),
        "conflicts": json.loads(row["conflicts"]),
    }
