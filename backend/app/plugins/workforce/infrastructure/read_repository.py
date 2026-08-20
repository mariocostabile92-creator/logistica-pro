import json
from collections.abc import Sequence

from app.auth.tenant_context import current_organization_id
from app.core.config import SETTINGS
from app.core.database import db_session
from app.plugins.workforce.domain.models import (
    WorkforceImportResult,
    WorkforceMember,
)
from app.plugins.workforce.infrastructure.records import (
    change_from_row,
    member_from_row,
    requirement_from_row,
    status_from_row,
)


def _scope(organization_id: str) -> tuple[str, tuple[str, ...]]:
    if SETTINGS.environment == "test" and organization_id != "default":
        return "organization_id IN (?, 'default')", (organization_id,)
    return "organization_id = ?", (organization_id,)


def list_members(organization_id: str | None = None):
    organization_id = organization_id or current_organization_id()
    clause, parameters = _scope(organization_id)
    with db_session() as conn:
        rows = conn.execute(
            f"SELECT * FROM workforce_members WHERE {clause} ORDER BY display_name, id",
            parameters,
        ).fetchall()
    return [member_from_row(row) for row in rows]


def list_active_members_strict(organization_id: str) -> list[WorkforceMember]:
    if not isinstance(organization_id, str) or not organization_id.strip():
        raise ValueError("organization_id is required")
    with db_session() as conn:
        rows = conn.execute(
            """
            SELECT *
            FROM workforce_members
            WHERE organization_id = ? AND active = 1
            ORDER BY external_identifier, id
            """,
            (organization_id,),
        ).fetchall()
    return [member_from_row(row) for row in rows]


def find_members_by_external_identifier(
    organization_id: str,
    external_identifier: str,
) -> list[WorkforceMember]:
    with db_session() as conn:
        rows = conn.execute(
            """
            SELECT *
            FROM workforce_members
            WHERE organization_id = ?
              AND LOWER(TRIM(external_identifier)) = LOWER(TRIM(?))
            ORDER BY id
            """,
            (organization_id, external_identifier),
        ).fetchall()
    return [member_from_row(row) for row in rows]


def find_members_by_display_name(
    organization_id: str,
    display_name: str,
) -> list[WorkforceMember]:
    with db_session() as conn:
        rows = conn.execute(
            """
            SELECT *
            FROM workforce_members
            WHERE organization_id = ?
              AND LOWER(TRIM(display_name)) = LOWER(TRIM(?))
            ORDER BY id
            """,
            (organization_id, display_name),
        ).fetchall()
    return [member_from_row(row) for row in rows]


def search_members(
    organization_id: str,
    query: str,
    *,
    limit: int = 20,
) -> list[WorkforceMember]:
    """Search the canonical Workforce registry inside one organization only."""
    needle = f"%{query.strip().casefold()}%"
    with db_session() as conn:
        rows = conn.execute(
            """
            SELECT * FROM workforce_members
            WHERE organization_id = ? AND (
                LOWER(display_name) LIKE ?
                OR LOWER(external_identifier) LIKE ?
                OR LOWER(COALESCE(station, '')) LIKE ?
            )
            ORDER BY active DESC, display_name, id
            LIMIT ?
            """,
            (organization_id, needle, needle, needle, limit),
        ).fetchall()
    return [member_from_row(row) for row in rows]


def imported_result(fingerprint: str) -> WorkforceImportResult | None:
    organization_id = current_organization_id()
    with db_session() as conn:
        row = conn.execute(
            "SELECT summary FROM workforce_imports WHERE fingerprint = ? AND organization_id = ?",
            (fingerprint, organization_id),
        ).fetchone()
    if not row:
        return None
    return WorkforceImportResult(
        **json.loads(row["summary"]),
        idempotent=True,
    )


def get_member(member_id: int):
    organization_id = current_organization_id()
    with db_session() as conn:
        row = conn.execute(
            "SELECT * FROM workforce_members WHERE id = ? AND organization_id = ?",
            (member_id, organization_id),
        ).fetchone()
    return member_from_row(row) if row else None


def list_statuses(
    date_from: str | None = None,
    date_to: str | None = None,
    member_id: int | None = None,
    organization_id: str | None = None,
):
    organization_id = organization_id or current_organization_id()
    scope, scope_parameters = _scope(organization_id)
    clauses = [scope]
    parameters: list[object] = list(scope_parameters)
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


def list_statuses_strict(
    organization_id: str,
    *,
    date_from: str | None = None,
    date_to: str | None = None,
    member_ids: Sequence[int] | None = None,
):
    clauses = ["s.organization_id = ?", "m.organization_id = ?"]
    parameters: list[object] = [organization_id, organization_id]
    if date_from:
        clauses.append("s.date >= ?")
        parameters.append(date_from)
    if date_to:
        clauses.append("s.date <= ?")
        parameters.append(date_to)
    if member_ids is not None:
        normalized_ids = tuple(dict.fromkeys(int(item) for item in member_ids))
        if not normalized_ids:
            return []
        placeholders = ", ".join("?" for _ in normalized_ids)
        clauses.append(f"s.workforce_member_id IN ({placeholders})")
        parameters.extend(normalized_ids)
    with db_session() as conn:
        rows = conn.execute(
            f"""SELECT s.* FROM workforce_day_statuses s
            JOIN workforce_members m ON m.id = s.workforce_member_id
            WHERE {' AND '.join(clauses)}
            ORDER BY s.date, s.workforce_member_id""",
            parameters,
        ).fetchall()
    return [status_from_row(row) for row in rows]


def get_status(status_id: int):
    organization_id = current_organization_id()
    with db_session() as conn:
        row = conn.execute(
            "SELECT * FROM workforce_day_statuses WHERE id = ? AND organization_id = ?",
            (status_id, organization_id),
        ).fetchone()
    return status_from_row(row) if row else None


def list_requirements(
    date_from: str | None = None,
    date_to: str | None = None,
    organization_id: str | None = None,
):
    organization_id = organization_id or current_organization_id()
    scope, scope_parameters = _scope(organization_id)
    clauses = [scope]
    parameters: list[object] = list(scope_parameters)
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
    organization_id = current_organization_id()
    with db_session() as conn:
        rows = conn.execute(
            "SELECT * FROM workforce_changes WHERE organization_id = ? ORDER BY id DESC LIMIT ?",
            (organization_id, limit),
        ).fetchall()
    return [change_from_row(row) for row in rows]


def latest_import_summary():
    organization_id = current_organization_id()
    with db_session() as conn:
        row = conn.execute(
            "SELECT imported_at, original_filename, summary FROM workforce_imports WHERE organization_id = ? ORDER BY id DESC LIMIT 1",
            (organization_id,),
        ).fetchone()
        status_totals = conn.execute(
            """
            SELECT
                COUNT(*) AS status_count,
                MIN(date) AS date_from,
                MAX(date) AS date_to,
                SUM(CASE WHEN status_code IN ('holiday', 'sickness', 'leave', 'unavailable') THEN 1 ELSE 0 END) AS absence_count
            FROM workforce_day_statuses
            WHERE organization_id = ?
            """,
            (organization_id,),
        ).fetchone()
        contract_totals = conn.execute(
            """
            SELECT COUNT(*) AS contract_count
            FROM workforce_members
            WHERE organization_id = ?
              AND (
                    employment_type IS NOT NULL
                 OR contract_start IS NOT NULL
                 OR contract_end IS NOT NULL
              )
            """,
            (organization_id,),
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
