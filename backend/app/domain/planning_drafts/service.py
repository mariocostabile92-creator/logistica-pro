from collections.abc import Callable, Mapping
from datetime import datetime

from app.domain.planning_drafts.errors import (
    PlanningDraftInvalidStateError,
    PlanningDraftNotFoundError,
    PlanningDraftSnapshotNotFoundError,
    PlanningDraftVersionConflictError,
)
from app.domain.planning_drafts.models import (
    PlanningDraft,
    PlanningDraftChange,
    PlanningDraftChangeMetadata,
    PlanningDraftChangeType,
    PlanningDraftMetadata,
    PlanningDraftScope,
    PlanningDraftSnapshot,
    PlanningDraftState,
    PlanningDraftVersion,
    PlanningDraftWorkspace,
)
from app.domain.planning_drafts.repository import PlanningDraftRepository


class PlanningDraftService:
    def __init__(
        self,
        *,
        repository: PlanningDraftRepository,
        clock: Callable[[], datetime],
        identifier_factory: Callable[[], str],
    ) -> None:
        self._repository = repository
        self._clock = clock
        self._identifier_factory = identifier_factory

    def current(self, scope: PlanningDraftScope) -> PlanningDraftWorkspace:
        draft = self._repository.get_active(scope)
        if draft is None:
            return PlanningDraftWorkspace(state=PlanningDraftState.EMPTY)
        return self._workspace(draft)

    def get_history(self, draft_id: str):
        self._require_draft(draft_id, active_only=False)
        return self._repository.get_history(draft_id, limit=100)

    def create(
        self,
        *,
        scope: PlanningDraftScope,
        metadata: PlanningDraftMetadata,
        actor: str,
    ) -> PlanningDraftWorkspace:
        now = self._clock()
        draft_id = self._new_id("draft")
        version = PlanningDraftVersion(
            number=1,
            created_at=now,
            created_by=actor,
        )
        draft = PlanningDraft(
            draft_id=draft_id,
            scope=scope,
            metadata=metadata,
            state=PlanningDraftState.CREATED,
            version=version,
            created_at=now,
            updated_at=now,
        )
        snapshot = self._snapshot(draft)
        change = self._change(
            draft=draft,
            change_type=PlanningDraftChangeType.CREATED,
            actor=actor,
            summary="Draft creato.",
            from_version=None,
        )
        self._repository.create(draft, snapshot, change)
        return self._workspace(draft)

    def update_metadata(
        self,
        *,
        draft_id: str,
        expected_version: int,
        changes: Mapping[str, object],
        actor: str,
    ) -> PlanningDraftWorkspace:
        current = self._require_active(draft_id, expected_version)
        values = current.metadata.model_dump()
        values.update(changes)
        metadata = PlanningDraftMetadata.model_validate(values)
        if metadata == current.metadata:
            return self._workspace(current)
        changed_fields = tuple(
            key for key in changes if values.get(key) != getattr(current.metadata, key)
        )
        return self._transition(
            current=current,
            state=PlanningDraftState.DIRTY,
            metadata=metadata,
            actor=actor,
            change_type=PlanningDraftChangeType.METADATA_UPDATED,
            summary="Metadati Draft aggiornati.",
            change_metadata={"fields": ",".join(changed_fields)},
        )

    def save(
        self,
        *,
        draft_id: str,
        expected_version: int,
        actor: str,
    ) -> PlanningDraftWorkspace:
        current = self._require_active(draft_id, expected_version)
        if current.state not in {
            PlanningDraftState.CREATED,
            PlanningDraftState.DIRTY,
        }:
            raise PlanningDraftInvalidStateError(
                "Solo un Draft creato o modificato puo essere salvato."
            )
        return self._transition(
            current=current,
            state=PlanningDraftState.SAVED,
            metadata=current.metadata,
            actor=actor,
            change_type=PlanningDraftChangeType.SAVED,
            summary="Draft salvato.",
        )

    def restore(
        self,
        *,
        draft_id: str,
        expected_version: int,
        target_version: int,
        actor: str,
    ) -> PlanningDraftWorkspace:
        current = self._require_active(draft_id, expected_version)
        if target_version >= current.version.number:
            raise PlanningDraftInvalidStateError(
                "La versione da ripristinare deve precedere quella corrente."
            )
        target = self._repository.get_snapshot(draft_id, target_version)
        if target is None:
            raise PlanningDraftSnapshotNotFoundError(
                "Versione Draft non disponibile."
            )
        return self._transition(
            current=current,
            state=PlanningDraftState.SAVED,
            metadata=target.metadata,
            actor=actor,
            change_type=PlanningDraftChangeType.RESTORED,
            summary=f"Ripristinata la versione {target_version}.",
            restored_from_version=target_version,
            change_metadata={"restored_version": target_version},
        )

    def delete(
        self,
        *,
        draft_id: str,
        expected_version: int,
        actor: str,
    ) -> PlanningDraftWorkspace:
        current = self._require_active(draft_id, expected_version)
        return self._transition(
            current=current,
            state=PlanningDraftState.READ_ONLY,
            metadata=current.metadata,
            actor=actor,
            change_type=PlanningDraftChangeType.DELETED,
            summary="Draft eliminato dal workspace attivo.",
            deleted=True,
        )

    def _transition(
        self,
        *,
        current: PlanningDraft,
        state: PlanningDraftState,
        metadata: PlanningDraftMetadata,
        actor: str,
        change_type: PlanningDraftChangeType,
        summary: str,
        restored_from_version: int | None = None,
        change_metadata: Mapping[str, object] | None = None,
        deleted: bool = False,
    ) -> PlanningDraftWorkspace:
        now = self._clock()
        version = PlanningDraftVersion(
            number=current.version.number + 1,
            created_at=now,
            created_by=actor,
            restored_from_version=restored_from_version,
        )
        draft = PlanningDraft.model_validate(
            {
                **current.model_dump(),
                "metadata": metadata,
                "state": state,
                "version": version,
                "updated_at": now,
                "deleted_at": now if deleted else None,
            }
        )
        snapshot = self._snapshot(draft)
        change = self._change(
            draft=draft,
            change_type=change_type,
            actor=actor,
            summary=summary,
            from_version=current.version.number,
            metadata=change_metadata,
        )
        replaced = self._repository.replace(
            draft,
            snapshot,
            change,
            expected_version=current.version.number,
        )
        if not replaced:
            raise PlanningDraftVersionConflictError(
                "Il Draft e stato aggiornato da un'altra sessione."
            )
        return self._workspace(draft)

    def _require_active(
        self,
        draft_id: str,
        expected_version: int,
    ) -> PlanningDraft:
        draft = self._require_draft(draft_id, active_only=True)
        if draft.version.number != expected_version:
            raise PlanningDraftVersionConflictError(
                "La versione Draft non coincide con quella corrente."
            )
        return draft

    def _require_draft(
        self,
        draft_id: str,
        *,
        active_only: bool,
    ) -> PlanningDraft:
        draft = self._repository.get_by_id(draft_id)
        if draft is None or (active_only and draft.deleted_at is not None):
            raise PlanningDraftNotFoundError("Draft non disponibile.")
        return draft

    def _workspace(self, draft: PlanningDraft) -> PlanningDraftWorkspace:
        return PlanningDraftWorkspace(
            state=draft.state,
            draft=draft,
            history=self._repository.get_history(draft.draft_id, limit=20),
        )

    def _snapshot(self, draft: PlanningDraft) -> PlanningDraftSnapshot:
        return PlanningDraftSnapshot(
            snapshot_id=self._new_id("snapshot"),
            draft_id=draft.draft_id,
            state=draft.state,
            version=draft.version,
            metadata=draft.metadata,
        )

    def _change(
        self,
        *,
        draft: PlanningDraft,
        change_type: PlanningDraftChangeType,
        actor: str,
        summary: str,
        from_version: int | None,
        metadata: Mapping[str, object] | None = None,
    ) -> PlanningDraftChange:
        items = tuple(
            PlanningDraftChangeMetadata(key=str(key), value=str(value))
            for key, value in sorted((metadata or {}).items())
            if str(value)
        )
        return PlanningDraftChange(
            change_id=self._new_id("change"),
            draft_id=draft.draft_id,
            change_type=change_type,
            from_version=from_version,
            to_version=draft.version.number,
            actor=actor,
            occurred_at=draft.updated_at,
            summary=summary,
            metadata=items,
        )

    def _new_id(self, prefix: str) -> str:
        return f"{prefix}-{self._identifier_factory()}"
