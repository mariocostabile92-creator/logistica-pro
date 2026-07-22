from datetime import date

from app.domain.core_language import OperationalUnit
from app.domain.planning_drafts import (
    PlanningDraftHistory,
    PlanningDraftMetadata,
    PlanningDraftScope,
    PlanningDraftService,
    PlanningDraftWorkspace,
)


class PlanningDraftRuntime:
    def __init__(
        self,
        *,
        service: PlanningDraftService,
        actor: str = "private-beta",
    ) -> None:
        self._service = service
        self._actor = actor

    def current(
        self,
        *,
        organization_id: str,
        operational_unit: OperationalUnit,
        planning_date: date,
    ) -> PlanningDraftWorkspace:
        return self._service.current(
            self._scope(
                organization_id=organization_id,
                operational_unit=operational_unit,
                planning_date=planning_date,
            )
        )

    def create(
        self,
        *,
        organization_id: str,
        operational_unit: OperationalUnit,
        planning_date: date,
        metadata: PlanningDraftMetadata,
    ) -> PlanningDraftWorkspace:
        return self._service.create(
            scope=self._scope(
                organization_id=organization_id,
                operational_unit=operational_unit,
                planning_date=planning_date,
            ),
            metadata=metadata,
            actor=self._actor,
        )

    def update_metadata(
        self,
        *,
        draft_id: str,
        expected_version: int,
        changes: dict[str, object],
    ) -> PlanningDraftWorkspace:
        return self._service.update_metadata(
            draft_id=draft_id,
            expected_version=expected_version,
            changes=changes,
            actor=self._actor,
        )

    def save(
        self,
        *,
        draft_id: str,
        expected_version: int,
    ) -> PlanningDraftWorkspace:
        return self._service.save(
            draft_id=draft_id,
            expected_version=expected_version,
            actor=self._actor,
        )

    def restore(
        self,
        *,
        draft_id: str,
        expected_version: int,
        target_version: int,
    ) -> PlanningDraftWorkspace:
        return self._service.restore(
            draft_id=draft_id,
            expected_version=expected_version,
            target_version=target_version,
            actor=self._actor,
        )

    def delete(
        self,
        *,
        draft_id: str,
        expected_version: int,
    ) -> PlanningDraftWorkspace:
        return self._service.delete(
            draft_id=draft_id,
            expected_version=expected_version,
            actor=self._actor,
        )

    def history(self, draft_id: str) -> PlanningDraftHistory:
        return self._service.get_history(draft_id)

    @staticmethod
    def _scope(
        *,
        organization_id: str,
        operational_unit: OperationalUnit,
        planning_date: date,
    ) -> PlanningDraftScope:
        return PlanningDraftScope(
            organization_id=organization_id,
            operational_unit=operational_unit,
            planning_date=planning_date,
        )
