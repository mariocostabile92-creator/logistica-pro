from typing import Protocol

from app.domain.planning_drafts.models import (
    PlanningDraft,
    PlanningDraftChange,
    PlanningDraftHistory,
    PlanningDraftScope,
    PlanningDraftSnapshot,
)


class PlanningDraftRepository(Protocol):
    def get_active(self, scope: PlanningDraftScope) -> PlanningDraft | None: ...

    def get_by_id(self, draft_id: str) -> PlanningDraft | None: ...

    def get_snapshot(
        self,
        draft_id: str,
        version: int,
    ) -> PlanningDraftSnapshot | None: ...

    def get_history(
        self,
        draft_id: str,
        *,
        limit: int = 100,
    ) -> PlanningDraftHistory: ...

    def create(
        self,
        draft: PlanningDraft,
        snapshot: PlanningDraftSnapshot,
        change: PlanningDraftChange,
    ) -> None: ...

    def replace(
        self,
        draft: PlanningDraft,
        snapshot: PlanningDraftSnapshot,
        change: PlanningDraftChange,
        *,
        expected_version: int,
    ) -> bool: ...
