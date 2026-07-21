from app.core.database import db_session
from app.plugins.workforce.infrastructure.records import (
    change_from_row,
    member_from_row,
    requirement_from_row,
    status_from_row,
)


def list_members():
    with db_session() as conn:
        rows = conn.execute(
            "SELECT * FROM workforce_members ORDER BY display_name, id"
        ).fetchall()
    return [member_from_row(row) for row in rows]


def get_member(member_id: int):
    with db_session() as conn:
        row = conn.execute(
            "SELECT * FROM workforce_members WHERE id = ?", (member_id,)
        ).fetchone()
    return member_from_row(row) if row else None


def list_statuses(
    date_from: str | None = None,
    date_to: str | None = None,
    member_id: int | None = None,
):
    clauses = []
    parameters: list[object] = []
    if date_from:
        clauses.append("date >= ?")
        parameters.append(date_from)
    if date_to:
        clauses.append("date <= ?")
        parameters.append(date_to)
    if member_id:
        clauses.append("workforce_member_id = ?")
        parameters.append(member_id)
    where = " WHERE " + " AND ".join(clauses) if clauses else ""
    with db_session() as conn:
        rows = conn.execute(
            f"SELECT * FROM workforce_day_statuses{where} ORDER BY date, workforce_member_id",
            parameters,
        ).fetchall()
    return [status_from_row(row) for row in rows]


def get_status(status_id: int):
    with db_session() as conn:
        row = conn.execute(
            "SELECT * FROM workforce_day_statuses WHERE id = ?", (status_id,)
        ).fetchone()
    return status_from_row(row) if row else None


def list_requirements(date_from: str | None = None, date_to: str | None = None):
    clauses = []
    parameters: list[object] = []
    if date_from:
        clauses.append("date >= ?")
        parameters.append(date_from)
    if date_to:
        clauses.append("date <= ?")
        parameters.append(date_to)
    where = " WHERE " + " AND ".join(clauses) if clauses else ""
    with db_session() as conn:
        rows = conn.execute(
            f"SELECT * FROM workforce_requirements{where} ORDER BY date, operational_unit_id",
            parameters,
        ).fetchall()
    return [requirement_from_row(row) for row in rows]


def list_changes(limit: int = 100):
    with db_session() as conn:
        rows = conn.execute(
            "SELECT * FROM workforce_changes ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
    return [change_from_row(row) for row in rows]


def latest_import_summary():
    with db_session() as conn:
        row = conn.execute(
            "SELECT imported_at, original_filename, summary FROM workforce_imports ORDER BY id DESC LIMIT 1"
        ).fetchone()
    if not row:
        return None
    import json
    return {
        "imported_at": row["imported_at"],
        "original_filename": row["original_filename"],
        "summary": json.loads(row["summary"]),
    }
