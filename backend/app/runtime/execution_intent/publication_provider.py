from app.domain.core_language import OperationalUnit
from app.domain.execution_intent import (
    ExecutionIntentScope,
    ExecutionPublicationReference,
    ExecutionPublicationStatus,
)
from app.domain.planning_publication import PlanningPublicationScope
from app.repositories.planning_publication_repository import (
    SqlPlanningPublicationRepository,
)


class SqlExecutionPublicationProvider:
    def __init__(self) -> None:
        self._repository = SqlPlanningPublicationRepository()

    def get(
        self,
        scope: ExecutionIntentScope,
    ) -> ExecutionPublicationReference | None:
        publication = self._repository.get_current(
            PlanningPublicationScope(
                organization_id=scope.organization_id,
                operational_unit=OperationalUnit(
                    external_identifier=scope.operational_unit_id,
                ),
                planning_date=scope.planning_date,
            )
        )
        if publication is None:
            return None
        return ExecutionPublicationReference(
            organization_id=publication.scope.organization_id,
            operational_unit_id=(
                publication.scope.operational_unit.external_identifier
            ),
            planning_date=publication.scope.planning_date,
            publication_id=publication.publication_id,
            publication_version=publication.version,
            fingerprint=publication.fingerprint,
            status=ExecutionPublicationStatus.PUBLISHED,
        )
