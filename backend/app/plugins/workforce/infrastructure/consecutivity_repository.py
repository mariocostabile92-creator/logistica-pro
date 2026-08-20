from datetime import date, timedelta
import json

from app.core.database import db_session
from app.core.config import SETTINGS
from app.plugins.workforce.domain.consecutivity import (
    ConsecutivityOverride,
    ConsecutivityPolicy,
)
from app.utils.date_utils import utc_now_iso


DEFAULT_WARNING_THRESHOLD = 5
DEFAULT_REST_REQUIRED_THRESHOLD = 6
DEFAULT_REST_BREAK_DAYS = 1


def _policy(row, organization_id: str) -> ConsecutivityPolicy:
    return ConsecutivityPolicy(
        organization_id=organization_id,
        warning_threshold=int(row["warning_threshold"]) if row else DEFAULT_WARNING_THRESHOLD,
        rest_required_threshold=int(row["rest_required_threshold"]) if row else DEFAULT_REST_REQUIRED_THRESHOLD,
        rest_break_days=int(row["rest_break_days"]) if row else DEFAULT_REST_BREAK_DAYS,
        updated_by=row["updated_by"] if row else "platform",
        updated_at=row["updated_at"] if row else utc_now_iso(),
    )


def get_policy(organization_id: str) -> ConsecutivityPolicy:
    with db_session() as conn:
        row = conn.execute(
            "SELECT * FROM workforce_consecutivity_policies WHERE organization_id = ?",
            (organization_id,),
        ).fetchone()
    return _policy(row, organization_id)


def save_policy(organization_id: str, values: dict[str, int], actor: str) -> ConsecutivityPolicy:
    now = utc_now_iso()
    with db_session() as conn:
        conn.execute(
            """
            INSERT INTO workforce_consecutivity_policies (
                organization_id, warning_threshold, rest_required_threshold,
                rest_break_days, updated_by, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(organization_id) DO UPDATE SET
                warning_threshold = excluded.warning_threshold,
                rest_required_threshold = excluded.rest_required_threshold,
                rest_break_days = excluded.rest_break_days,
                updated_by = excluded.updated_by,
                updated_at = excluded.updated_at
            """,
            (
                organization_id, values["warning_threshold"],
                values["rest_required_threshold"], values["rest_break_days"],
                actor, now,
            ),
        )
        conn.execute(
            """
            INSERT INTO workforce_changes (
                entity_type, entity_id, actor, timestamp, before_value,
                after_value, reason, source, organization_id
            ) VALUES ('consecutivity_policy', ?, ?, ?, NULL, ?, 'policy_updated', 'manual', ?)
            """,
            (organization_id, actor, now, json.dumps(values, ensure_ascii=False), organization_id),
        )
    return get_policy(organization_id)


def _override(row) -> ConsecutivityOverride:
    return ConsecutivityOverride(**{key: row[key] for key in row.keys()})


def active_overrides(organization_id: str, operation_date: str) -> dict[int, ConsecutivityOverride]:
    with db_session() as conn:
        rows = conn.execute(
            """
            SELECT * FROM workforce_consecutivity_overrides
            WHERE organization_id = ? AND revoked_at IS NULL
              AND operation_date <= ? AND valid_until >= ?
            ORDER BY created_at DESC
            """,
            (organization_id, operation_date, operation_date),
        ).fetchall()
    result: dict[int, ConsecutivityOverride] = {}
    for row in rows:
        item = _override(row)
        result.setdefault(item.workforce_member_id, item)
    return result


def expired_overrides(
    organization_id: str, operation_date: str,
) -> dict[int, ConsecutivityOverride]:
    with db_session() as conn:
        rows = conn.execute(
            """SELECT * FROM workforce_consecutivity_overrides
            WHERE organization_id = ? AND revoked_at IS NULL AND valid_until < ?
            ORDER BY created_at DESC""",
            (organization_id, operation_date),
        ).fetchall()
    result: dict[int, ConsecutivityOverride] = {}
    for row in rows:
        item = _override(row)
        result.setdefault(item.workforce_member_id, item)
    return result


def override_candidates_for_period(
    organization_id: str,
    period_end: str,
) -> list[ConsecutivityOverride]:
    """Load once all non-revoked overrides that can affect the period."""
    with db_session() as conn:
        rows = conn.execute(
            """SELECT * FROM workforce_consecutivity_overrides
            WHERE organization_id = ? AND revoked_at IS NULL
              AND operation_date <= ?
            ORDER BY created_at DESC""",
            (organization_id, period_end),
        ).fetchall()
    return [_override(row) for row in rows]


def override_history(organization_id: str, member_id: int) -> list[ConsecutivityOverride]:
    with db_session() as conn:
        rows = conn.execute(
            """SELECT * FROM workforce_consecutivity_overrides
            WHERE organization_id = ? AND workforce_member_id = ?
            ORDER BY created_at DESC""",
            (organization_id, member_id),
        ).fetchall()
    return [_override(row) for row in rows]


def insert_override(values: dict[str, object]) -> ConsecutivityOverride:
    with db_session() as conn:
        conn.execute(
            """INSERT INTO workforce_consecutivity_overrides (
                id, organization_id, workforce_member_id, operation_date,
                valid_until, target_callability, reason, created_by,
                created_at, revoked_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, NULL)""",
            (
                values["id"], values["organization_id"], values["workforce_member_id"],
                values["operation_date"], values["valid_until"],
                values["target_callability"], values["reason"],
                values["created_by"], values["created_at"],
            ),
        )
        conn.execute(
            """INSERT INTO workforce_changes (
                entity_type, entity_id, actor, timestamp, before_value,
                after_value, reason, source, organization_id
            ) VALUES ('consecutivity_override', ?, ?, ?, NULL, ?, 'override_created', 'manual', ?)""",
            (
                values["id"], values["created_by"], values["created_at"],
                json.dumps(values, ensure_ascii=False), values["organization_id"],
            ),
        )
    return _override_by_id(str(values["id"]), str(values["organization_id"]))


def _override_by_id(override_id: str, organization_id: str) -> ConsecutivityOverride:
    with db_session() as conn:
        row = conn.execute(
            "SELECT * FROM workforce_consecutivity_overrides WHERE id = ? AND organization_id = ?",
            (override_id, organization_id),
        ).fetchone()
    if not row:
        raise LookupError("Override non trovato.")
    return _override(row)


def _source_rows(
    organization_id: str,
    date_from: str,
    date_to: str,
    *,
    allow_test_default_scope: bool,
) -> dict[str, list[dict]]:
    use_test_default_scope = allow_test_default_scope and SETTINGS.environment == "test"
    organization_operator = "IN (?, 'default')" if use_test_default_scope else "= ?"
    planning_scope = (
        "(p.organization_id = ? OR p.organization_id IS NULL OR p.organization_id = 'default')"
        if use_test_default_scope
        else "p.organization_id = ?"
    )
    with db_session() as conn:
        statuses = conn.execute(
            f"""SELECT s.*, m.external_identifier FROM workforce_day_statuses s
            JOIN workforce_members m ON m.id = s.workforce_member_id
            WHERE s.date BETWEEN ? AND ?
              AND s.organization_id {organization_operator}
              AND m.organization_id {organization_operator}""",
            (date_from, date_to, organization_id, organization_id),
        ).fetchall()
        plannings = conn.execute(
            f"""SELECT p.operation_date, p.status, a.driver_id
            FROM assignments a JOIN plannings p ON p.id = a.planning_id
            WHERE p.operation_date BETWEEN ? AND ?
              AND p.status IN ('confirmed', 'published')
              AND a.driver_id IS NOT NULL
              AND {planning_scope}""",
            (date_from, date_to, organization_id),
        ).fetchall()
        finalized_days = conn.execute(
            f"""SELECT operation_date, status FROM plannings p
            WHERE operation_date BETWEEN ? AND ?
              AND status IN ('confirmed', 'published')
              AND {planning_scope}""",
            (date_from, date_to, organization_id),
        ).fetchall()
        journal = conn.execute(
            """SELECT m.declared_driver_identifier,
                COALESCE(s.operational_date, SUBSTR(m.occurred_at, 1, 10)) AS operation_date,
                m.id
            FROM asset_movements m JOIN journal_sessions s ON s.id = m.session_id
            WHERE m.organization_id = ? AND s.status = 'completed'
              AND COALESCE(s.operational_date, SUBSTR(m.occurred_at, 1, 10)) BETWEEN ? AND ?""",
            (organization_id, date_from, date_to),
        ).fetchall()
    def rows(items):
        return [{key: row[key] for key in row.keys()} for row in items]
    return {
        "statuses": rows(statuses), "plannings": rows(plannings),
        "finalized_days": rows(finalized_days), "journal": rows(journal),
    }


def source_rows(organization_id: str, date_from: str, date_to: str) -> dict[str, list[dict]]:
    return _source_rows(
        organization_id,
        date_from,
        date_to,
        allow_test_default_scope=True,
    )


def source_rows_for_organization(
    organization_id: str,
    date_from: str,
    date_to: str,
) -> dict[str, list[dict]]:
    return _source_rows(
        organization_id,
        date_from,
        date_to,
        allow_test_default_scope=False,
    )


def analysis_window(operation_date: str, lookback_days: int = 60, lookahead_days: int = 60) -> tuple[str, str]:
    target = date.fromisoformat(operation_date)
    return (
        (target - timedelta(days=lookback_days)).isoformat(),
        (target + timedelta(days=lookahead_days)).isoformat(),
    )


def analysis_period_window(
    period_start: str,
    period_end: str,
    lookback_days: int = 60,
    lookahead_days: int = 60,
) -> tuple[str, str]:
    start = date.fromisoformat(period_start)
    end = date.fromisoformat(period_end)
    return (
        (start - timedelta(days=lookback_days)).isoformat(),
        (end + timedelta(days=lookahead_days)).isoformat(),
    )
