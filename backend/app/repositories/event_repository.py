import json

from app.auth.tenant_context import current_organization_id
from app.core.database import db_session
from app.domain.operation_events import OperationEvent
from app.domain.planning_diff import PlanningDiff


def save_event(event: OperationEvent, diff: PlanningDiff) -> OperationEvent:
    organization_id = current_organization_id()
    with db_session() as conn:
        owned = conn.execute(
            "SELECT 1 FROM plannings WHERE id=? AND organization_id=?",
            (event.planning_id, organization_id),
        ).fetchone()
        if not owned:
            raise LookupError("Planning non trovato.")
        cursor = conn.execute(
            """
            INSERT INTO planning_events (
                planning_id, event_type, entity_type, entity_id, reason,
                simulated, applied, impact_summary, payload, diff, actor,
                created_at, applied_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event.planning_id,
                event.event_type.value,
                event.entity_type.value,
                event.entity_id,
                event.reason,
                int(event.simulated),
                int(event.applied),
                event.impact_summary,
                json.dumps(event.payload, ensure_ascii=False),
                json.dumps(diff.model_dump(mode="json"), ensure_ascii=False),
                event.actor,
                event.created_at,
                event.applied_at,
            ),
        )
        event.event_id = int(cursor.lastrowid)
    return event


def list_events(planning_id: int) -> list[dict[str, object]]:
    organization_id = current_organization_id()
    with db_session() as conn:
        rows = conn.execute(
            """
            SELECT e.* FROM planning_events e
            JOIN plannings p ON p.id=e.planning_id
            WHERE e.planning_id = ? AND p.organization_id = ?
            ORDER BY e.id ASC
            """,
            (planning_id, organization_id),
        ).fetchall()
    return [
        {
            "event_id": row["id"],
            "planning_id": row["planning_id"],
            "event_type": row["event_type"],
            "entity_type": row["entity_type"],
            "entity_id": row["entity_id"],
            "reason": row["reason"],
            "simulated": bool(row["simulated"]),
            "applied": bool(row["applied"]),
            "impact_summary": row["impact_summary"],
            "payload": json.loads(row["payload"]),
            "diff": json.loads(row["diff"]),
            "actor": row["actor"],
            "created_at": row["created_at"],
            "applied_at": row["applied_at"],
        }
        for row in rows
    ]
