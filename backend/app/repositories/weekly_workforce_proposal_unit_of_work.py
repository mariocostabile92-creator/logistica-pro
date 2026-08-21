from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any

from app.core.database import db_session
from app.domain.workforce_auto_planning.weekly_planning_input_snapshot import (
    WeeklyPlanningInputSnapshot,
)
from app.domain.workforce_auto_planning.weekly_proposal_composer import (
    ComposedWeeklyWorkforceProposal,
)
from app.domain.workforce_auto_planning.weekly_proposal_event import (
    WeeklyWorkforceProposalEvent,
)
from app.repositories.weekly_workforce_proposal_event_repository import (
    SqlWeeklyWorkforceProposalEventRepository,
)
from app.repositories.weekly_workforce_proposal_repository import (
    SqlWeeklyWorkforceProposalRepository,
)


@dataclass(frozen=True)
class _ConnectionBoundProposalWriter:
    connection: Any
    repository: SqlWeeklyWorkforceProposalRepository

    def save_revision(
        self,
        *,
        organization_id: str,
        snapshot: WeeklyPlanningInputSnapshot,
        aggregate: ComposedWeeklyWorkforceProposal,
    ) -> ComposedWeeklyWorkforceProposal:
        return self.repository._save_revision_with_connection(
            conn=self.connection,
            organization_id=organization_id,
            snapshot=snapshot,
            aggregate=aggregate,
        )


@dataclass(frozen=True)
class _ConnectionBoundEventWriter:
    connection: Any
    repository: SqlWeeklyWorkforceProposalEventRepository

    def append_event(
        self,
        *,
        organization_id: str,
        event: WeeklyWorkforceProposalEvent,
    ) -> WeeklyWorkforceProposalEvent:
        return self.repository._append_event_with_connection(
            conn=self.connection,
            organization_id=organization_id,
            event=event,
        )


@dataclass(frozen=True)
class WeeklyWorkforceProposalTransaction:
    proposals: _ConnectionBoundProposalWriter
    events: _ConnectionBoundEventWriter


class WeeklyWorkforceProposalUnitOfWork:
    def __init__(
        self,
        *,
        proposal_repository: SqlWeeklyWorkforceProposalRepository | None = None,
        event_repository: SqlWeeklyWorkforceProposalEventRepository | None = None,
    ) -> None:
        self._proposal_repository = (
            proposal_repository or SqlWeeklyWorkforceProposalRepository()
        )
        self._event_repository = (
            event_repository or SqlWeeklyWorkforceProposalEventRepository()
        )

    @contextmanager
    def transaction(self) -> Iterator[WeeklyWorkforceProposalTransaction]:
        with db_session() as conn:
            yield WeeklyWorkforceProposalTransaction(
                proposals=_ConnectionBoundProposalWriter(
                    connection=conn,
                    repository=self._proposal_repository,
                ),
                events=_ConnectionBoundEventWriter(
                    connection=conn,
                    repository=self._event_repository,
                ),
            )
