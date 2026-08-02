import json

from app.core.database import db_session
from app.plugins.workforce.domain.models import WorkforceImportResult
from app.plugins.workforce.infrastructure.records import (
    change_from_row,
    member_from_row,
    requirement_from_row,
    status_from_row,
)


def list_members(organization_id: str | None = None):
    where = " WHERE organization_id IN (?, 'default')" if organization_id else ""
    parameters = (organization_id,) if organization_id else ()
    with db_session() as conn:
        rows = conn.execute(
            f"SELECT * FROM workforce_members{where} ORDER BY display_name, id",
            parameters,
        ).fetchall()
    return [member_from_row(row) for row in rows]


def imported_result(fingerprint: str) -> WorkforceImportResult | None:
    with db_session() as conn:
        row = conn.execute(
            "SELECT summary FROM workforce_imports WHERE fingerprint = ?",
            (fingerprint,),
        ).fetchone()
    if not row:
        return None
    return WorkforceImportResult(
        **json.loads(row["summary"]),
        idempotent=True,
    )


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
    organization_id: str | None = None,
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
    if organization_id:
        clauses.append("organization_id IN (?, 'default')")
        parameters.append(organization_id)
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


def list_requirements(
    date_from: str | None = None,
    date_to: str | None = None,
    organization_id: str | None = None,
):
    clauses = []
    parameters: list[object] = []
    if date_from:
        clauses.append("date >= ?")
        parameters.append(date_from)
    if date_to:
        clauses.append("date <= ?")
        parameters.append(date_to)
    if organization_id:
        clauses.append("organization_id IN (?, 'default')")
        parameters.append(organization_id)
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
        status_totals = conn.execute(
            """
            SELECT
                COUNT(*) AS status_count,
                MIN(date) AS date_from,
                MAX(date) AS date_to,
                SUM(CASE WHEN status_code IN ('holiday', 'sickness', 'leave', 'unavailable') THEN 1 ELSE 0 END) AS absence_count
            FROM workforce_day_statuses
            """
        ).fetchone()
        contract_totals = conn.execute(
            """
            SELECT COUNT(*) AS contract_count
            FROM workforce_members
            WHERE employment_type IS NOT NULL
               OR contract_start IS NOT NULL
               OR contract_end IS NOT NULL
            """
        ).fetchone()
    if not row:
        return None
    summary = json.loads(row["summary"])
    summary.update({
        "status_count": int(status_totals["status_count"] or 0),
        "date_from": status_totals["date_from"],
        "date_to": status_totals["date_to"],
        "contracts_detected": int(contract_totals["contract_count"] or 0),
        "absences_detected": int(status_totals["absence_count"] or 0),
    })
    return {
        "imported_at": row["imported_at"],
        "original_filename": row["original_filename"],
        "source": "Excel",
        "summary": summary,
    }
