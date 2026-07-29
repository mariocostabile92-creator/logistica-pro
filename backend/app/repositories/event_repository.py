import json

from app.core.database import db_session
from app.domain.operation_events import OperationEvent
from app.domain.planning_diff import PlanningDiff


def save_event(event: OperationEvent, diff: PlanningDiff) -> OperationEvent:
    with db_session() as conn:
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
    with db_session() as conn:
        rows = conn.execute(
            """
            SELECT * FROM planning_events
            WHERE planning_id = ?
            ORDER BY id ASC
            """,
            (planning_id,),
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
