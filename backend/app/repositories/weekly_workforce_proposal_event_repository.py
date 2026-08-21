import json
import sqlite3
from typing import Any

from app.core.database import db_session
from app.domain.workforce_auto_planning.weekly_proposal_event import (
    WeeklyWorkforceProposalEvent,
)
from app.domain.workforce_auto_planning.weekly_proposal_event_repository import (
    WeeklyWorkforceProposalEventAlreadyExistsError,
    validate_weekly_workforce_proposal_event_scope,
)


class WeeklyWorkforceProposalEventRevisionNotFoundError(RuntimeError):
    pass


def _canonical_payload_json(event: WeeklyWorkforceProposalEvent) -> str:
    return json.dumps(
        event.payload.model_dump(mode="json"),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


class SqlWeeklyWorkforceProposalEventRepository:
    def append_event(
        self,
        *,
        organization_id: str,
        event: WeeklyWorkforceProposalEvent,
    ) -> WeeklyWorkforceProposalEvent:
        with db_session() as conn:
            return self._append_event_with_connection(
                conn=conn,
                organization_id=organization_id,
                event=event,
            )

    def _append_event_with_connection(
        self,
        *,
        conn: Any,
        organization_id: str,
        event: WeeklyWorkforceProposalEvent,
    ) -> WeeklyWorkforceProposalEvent:
        validate_weekly_workforce_proposal_event_scope(
            organization_id=organization_id,
            event=event,
        )
        revision = conn.execute(
            """
            SELECT 1
            FROM weekly_workforce_proposals
            WHERE organization_id = ?
              AND proposal_id = ?
              AND version = ?
            """,
            (
                organization_id,
                event.proposal_id,
                event.proposal_version,
            ),
        ).fetchone()
        if revision is None:
            raise WeeklyWorkforceProposalEventRevisionNotFoundError(
                "proposal revision for event was not found"
            )

        duplicate = conn.execute(
            """
            SELECT 1
            FROM weekly_workforce_proposal_events
            WHERE organization_id = ?
              AND proposal_id = ?
              AND proposal_version = ?
              AND event_id = ?
            """,
            (
                organization_id,
                event.proposal_id,
                event.proposal_version,
                event.event_id,
            ),
        ).fetchone()
        if duplicate is not None:
            raise WeeklyWorkforceProposalEventAlreadyExistsError(
                "proposal event already exists"
            )

        try:
            conn.execute(
                """
                INSERT INTO weekly_workforce_proposal_events (
                    organization_id, proposal_id, proposal_version,
                    event_id, event_type, actor_id, reason,
                    payload_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    organization_id,
                    event.proposal_id,
                    event.proposal_version,
                    event.event_id,
                    event.event_type,
                    event.actor_id,
                    event.reason,
                    _canonical_payload_json(event),
                    event.created_at.isoformat(),
                ),
            )
        except sqlite3.IntegrityError as exc:
            raise WeeklyWorkforceProposalEventAlreadyExistsError(
                "proposal event already exists"
            ) from exc
        return event
