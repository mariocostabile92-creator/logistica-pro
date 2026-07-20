import logging
from threading import Lock
from uuid import uuid4

from app.core.database import db_session
from app.utils.date_utils import utc_now_iso
from app.workspace import repository
from app.workspace.models import WorkspaceState
from app.workspace.schemas import (
    WorkspaceRemovedCounts,
    WorkspaceResetResponse,
)
from app.workspace.status_service import get_workspace_status


logger = logging.getLogger("operations_engine.workspace")
_RESET_LOCK = Lock()


class WorkspaceResetInProgressError(RuntimeError):
    pass


class WorkspaceResetFailedError(RuntimeError):
    pass


def reset_workspace(
    *,
    actor: str = "system/private-beta",
) -> WorkspaceResetResponse:
    if not _RESET_LOCK.acquire(blocking=False):
        raise WorkspaceResetInProgressError(
            "Un ripristino del workspace e gia in corso."
        )

    try:
        reset_id = str(uuid4())
        started_at = utc_now_iso()
        previous = get_workspace_status()
        repository.start_reset_audit(
            reset_id=reset_id,
            started_at=started_at,
            actor=actor,
            previous_state=previous.workspace_state.value,
        )

        removed: dict[str, int] = {}
        with db_session() as conn:
            removed = repository.reset_operational_data(conn)

        final_status = get_workspace_status()
        if final_status.workspace_state != WorkspaceState.EMPTY:
            raise RuntimeError("Workspace state verification failed.")

        completed_at = utc_now_iso()
        repository.complete_reset_audit(
            reset_id=reset_id,
            completed_at=completed_at,
            final_state=final_status.workspace_state.value,
            removed_counts=removed,
            outcome="completed",
        )
        idempotent = not any(removed.values())
        return WorkspaceResetResponse(
            reset_id=reset_id,
            workspace_state=WorkspaceState.EMPTY,
            idempotent=idempotent,
            message_code=(
                "workspace_already_empty"
                if idempotent
                else "workspace_reset_completed"
            ),
            removed_counts=WorkspaceRemovedCounts.model_validate(removed),
            completed_at=completed_at,
        )
    except Exception as exc:
        reset_id = locals().get("reset_id", "not-created")
        previous_state = (
            previous.workspace_state.value
            if "previous" in locals()
            else WorkspaceState.EMPTY.value
        )
        logger.exception("Workspace reset failed reset_id=%s", reset_id)
        completed_at = utc_now_iso()
        if reset_id != "not-created":
            try:
                repository.complete_reset_audit(
                    reset_id=reset_id,
                    completed_at=completed_at,
                    final_state=previous_state,
                    removed_counts={},
                    outcome="failed",
                    sanitized_error="workspace_reset_failed",
                )
            except Exception:
                logger.exception(
                    "Workspace reset audit update failed reset_id=%s",
                    reset_id,
                )
        raise WorkspaceResetFailedError(
            "Il workspace non e stato ripristinato. I dati sono rimasti invariati."
        ) from exc
    finally:
        _RESET_LOCK.release()
