import json
import sqlite3
from collections.abc import Iterable
from typing import Any

from pydantic import BaseModel

from app.core.database import db_session
from app.domain.core_language import OperationalUnit, TimeWindow
from app.domain.workforce_auto_planning.candidate_ranking import (
    RankedWorkforceCandidate,
)
from app.domain.workforce_auto_planning.coverage_gap import (
    CoverageGap,
    CoverageGapReason,
)
from app.domain.workforce_auto_planning.planning_preference import (
    WorkforcePlanningPreferenceSet,
)
from app.domain.workforce_auto_planning.proposed_shift_assignment import (
    ProposedAssignmentReason,
    ProposedShiftAssignment,
)
from app.domain.workforce_auto_planning.weekly_planning_input_snapshot import (
    WeeklyPlanningInputSnapshot,
)
from app.domain.workforce_auto_planning.weekly_proposal_composer import (
    ComposedWeeklyWorkforceProposal,
)
from app.domain.workforce_auto_planning.weekly_proposal_repository import (
    WeeklyWorkforceProposalOrganizationMismatchError,
    WeeklyWorkforceProposalRevisionAlreadyExistsError,
    WeeklyWorkforceProposalRevisionNotFoundError,
    WeeklyWorkforceProposalSnapshotMismatchError,
    validate_weekly_workforce_proposal_save_contract,
)
from app.domain.workforce_auto_planning.weekly_workforce_proposal import (
    WeeklyWorkforceProposal,
)
from app.domain.workforce_auto_planning.workforce_eligibility_decision import (
    WorkforceEligibilityDecision,
)


_ELIGIBILITY = "ELIGIBILITY"
_PREFERENCE_SET = "PREFERENCE_SET"
_RANKED_CANDIDATE = "RANKED_CANDIDATE"


def _required_identifier(value: str, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} is required")
    return value


def _positive_version(value: int) -> int:
    if type(value) is not int or value <= 0:
        raise ValueError("version must be a strict positive integer")
    return value


def _canonical_json(value: BaseModel | object) -> str:
    payload = value.model_dump(mode="json") if isinstance(value, BaseModel) else value
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _snapshot_from_row(row: Any) -> WeeklyPlanningInputSnapshot:
    try:
        snapshot = WeeklyPlanningInputSnapshot.model_validate_json(
            row["payload_json"]
        )
    except Exception as exc:
        raise WeeklyWorkforceProposalSnapshotMismatchError(
            "persisted snapshot payload is invalid"
        ) from exc

    expected = (
        (snapshot.organization_id, row["organization_id"]),
        (snapshot.snapshot_id, row["snapshot_id"]),
        (snapshot.period_start.isoformat(), row["period_start"]),
        (snapshot.period_end.isoformat(), row["period_end"]),
        (
            snapshot.operational_unit.external_identifier,
            row["operational_unit_identifier"],
        ),
        (snapshot.policy_set_identifier, row["policy_set_identifier"]),
        (snapshot.policy_set_version, row["policy_set_version"]),
        (snapshot.fingerprint, row["fingerprint"]),
    )
    if any(actual != persisted for actual, persisted in expected):
        raise WeeklyWorkforceProposalSnapshotMismatchError(
            "persisted snapshot payload does not match snapshot metadata"
        )
    return snapshot


def _proposal_from_row(row: Any) -> WeeklyWorkforceProposal:
    return WeeklyWorkforceProposal(
        proposal_id=row["proposal_id"],
        organization_id=row["organization_id"],
        period_start=row["period_start"],
        period_end=row["period_end"],
        operational_unit=OperationalUnit(
            external_identifier=row["operational_unit_identifier"],
            name=row["operational_unit_name"],
        ),
        version=row["version"],
        input_snapshot_id=row["input_snapshot_id"],
        input_fingerprint=row["input_fingerprint"],
        policy_set_identifier=row["policy_set_identifier"],
        policy_set_version=row["policy_set_version"],
        status=row["status"],
        created_at=row["created_at"],
    )


def _assignment_from_row(row: Any) -> ProposedShiftAssignment:
    reasons = tuple(
        ProposedAssignmentReason.model_validate(item)
        for item in json.loads(row["reasons_json"])
    )
    return ProposedShiftAssignment(
        assignment_id=row["assignment_id"],
        demand_trace_id=row["demand_trace_id"],
        organization_id=row["organization_id"],
        workforce_member_id=row["workforce_member_id"],
        date=row["operational_date"],
        operational_unit=OperationalUnit(
            external_identifier=row["operational_unit_identifier"],
            name=row["operational_unit_name"],
        ),
        shift_identifier=row["shift_identifier"],
        time_window=TimeWindow(
            external_identifier=row["time_window_identifier"],
            starts_at=row["starts_at"],
            ends_at=row["ends_at"],
        ),
        capability_or_workload=row["capability_or_workload"],
        origin=row["origin"],
        status=row["status"],
        deterministic_priority=row["deterministic_priority"],
        reasons=reasons,
        locked=bool(row["locked"]),
    )


def _gap_from_row(row: Any) -> CoverageGap:
    reasons_payload = json.loads(row["reasons_json"])
    return CoverageGap(
        demand_trace_id=row["demand_trace_id"],
        organization_id=row["organization_id"],
        date=row["operational_date"],
        operational_unit=OperationalUnit(
            external_identifier=row["operational_unit_identifier"],
            name=row["operational_unit_name"],
        ),
        time_window=TimeWindow(
            external_identifier=row["time_window_identifier"],
            starts_at=row["starts_at"],
            ends_at=row["ends_at"],
        ),
        capability_or_workload=row["capability_or_workload"],
        required_quantity=row["required_quantity"],
        proposed_quantity=row["proposed_quantity"],
        gap_quantity=row["gap_quantity"],
        reason=CoverageGapReason.model_validate(reasons_payload["reason"]),
        excluded_candidate_categories=tuple(
            reasons_payload["excluded_candidate_categories"]
        ),
    )


def _artifact_from_row(row: Any) -> BaseModel:
    model_by_type: dict[str, type[BaseModel]] = {
        _ELIGIBILITY: WorkforceEligibilityDecision,
        _PREFERENCE_SET: WorkforcePlanningPreferenceSet,
        _RANKED_CANDIDATE: RankedWorkforceCandidate,
    }
    try:
        model = model_by_type[row["artifact_type"]]
    except KeyError as exc:
        raise ValueError(
            f"unknown proposal explainability type: {row['artifact_type']}"
        ) from exc
    artifact = model.model_validate_json(row["payload_json"])
    if artifact.demand_trace_id != row["demand_trace_id"]:
        raise ValueError("explainability payload demand trace is inconsistent")
    if artifact.workforce_member_id != row["workforce_member_id"]:
        raise ValueError("explainability payload workforce member is inconsistent")
    return artifact


class SqlWeeklyWorkforceProposalRepository:
    def save_revision(
        self,
        *,
        organization_id: str,
        snapshot: WeeklyPlanningInputSnapshot,
        aggregate: ComposedWeeklyWorkforceProposal,
    ) -> ComposedWeeklyWorkforceProposal:
        with db_session() as conn:
            return self._save_revision_with_connection(
                conn=conn,
                organization_id=organization_id,
                snapshot=snapshot,
                aggregate=aggregate,
            )

    def _save_revision_with_connection(
        self,
        *,
        conn: Any,
        organization_id: str,
        snapshot: WeeklyPlanningInputSnapshot,
        aggregate: ComposedWeeklyWorkforceProposal,
    ) -> ComposedWeeklyWorkforceProposal:
        organization_id = _required_identifier(
            organization_id,
            field="organization_id",
        )
        validate_weekly_workforce_proposal_save_contract(
            organization_id=organization_id,
            snapshot=snapshot,
            aggregate=aggregate,
        )
        proposal = aggregate.proposal
        _required_identifier(proposal.proposal_id, field="proposal_id")
        _positive_version(proposal.version)

        duplicate = conn.execute(
            """
            SELECT 1
            FROM weekly_workforce_proposals
            WHERE organization_id = ?
              AND proposal_id = ?
              AND version = ?
            """,
            (organization_id, proposal.proposal_id, proposal.version),
        ).fetchone()
        if duplicate is not None:
            raise WeeklyWorkforceProposalRevisionAlreadyExistsError(
                "proposal revision already exists"
            )

        self._persist_or_validate_snapshot(conn, snapshot=snapshot)
        self._insert_proposal(conn, proposal=proposal)
        self._insert_assignments(conn, proposal=proposal, aggregate=aggregate)
        self._insert_gaps(conn, proposal=proposal, aggregate=aggregate)
        self._insert_explainability(
            conn,
            proposal=proposal,
            aggregate=aggregate,
        )
        return aggregate

    def get_revision(
        self,
        *,
        organization_id: str,
        proposal_id: str,
        version: int,
    ) -> ComposedWeeklyWorkforceProposal:
        organization_id = _required_identifier(
            organization_id,
            field="organization_id",
        )
        proposal_id = _required_identifier(proposal_id, field="proposal_id")
        version = _positive_version(version)
        with db_session() as conn:
            revisions = self._load_revisions(
                conn,
                organization_id=organization_id,
                proposal_id=proposal_id,
                version=version,
            )
        if not revisions:
            raise WeeklyWorkforceProposalRevisionNotFoundError(
                "proposal revision not found"
            )
        return revisions[0]

    def list_revisions(
        self,
        *,
        organization_id: str,
        proposal_id: str,
    ) -> tuple[ComposedWeeklyWorkforceProposal, ...]:
        organization_id = _required_identifier(
            organization_id,
            field="organization_id",
        )
        proposal_id = _required_identifier(proposal_id, field="proposal_id")
        with db_session() as conn:
            revisions = self._load_revisions(
                conn,
                organization_id=organization_id,
                proposal_id=proposal_id,
                version=None,
            )
        if not revisions:
            raise WeeklyWorkforceProposalRevisionNotFoundError(
                "proposal revisions not found"
            )
        return revisions

    def latest_revision(
        self,
        *,
        organization_id: str,
        proposal_id: str,
    ) -> ComposedWeeklyWorkforceProposal:
        organization_id = _required_identifier(
            organization_id,
            field="organization_id",
        )
        proposal_id = _required_identifier(proposal_id, field="proposal_id")
        with db_session() as conn:
            row = conn.execute(
                """
                SELECT MAX(version) AS version
                FROM weekly_workforce_proposals
                WHERE organization_id = ? AND proposal_id = ?
                """,
                (organization_id, proposal_id),
            ).fetchone()
            if row is None or row["version"] is None:
                raise WeeklyWorkforceProposalRevisionNotFoundError(
                    "proposal revisions not found"
                )
            revisions = self._load_revisions(
                conn,
                organization_id=organization_id,
                proposal_id=proposal_id,
                version=int(row["version"]),
            )
        return revisions[0]

    @staticmethod
    def _persist_or_validate_snapshot(conn: Any, *, snapshot: WeeklyPlanningInputSnapshot) -> None:
        row = conn.execute(
            """
            SELECT *
            FROM weekly_planning_input_snapshots
            WHERE organization_id = ? AND snapshot_id = ?
            """,
            (snapshot.organization_id, snapshot.snapshot_id),
        ).fetchone()
        if row is not None:
            persisted = _snapshot_from_row(row)
            consistency = (
                persisted.fingerprint == snapshot.fingerprint,
                persisted.period_start == snapshot.period_start,
                persisted.period_end == snapshot.period_end,
                persisted.operational_unit.external_identifier
                == snapshot.operational_unit.external_identifier,
                persisted.policy_set_identifier == snapshot.policy_set_identifier,
                persisted.policy_set_version == snapshot.policy_set_version,
            )
            if not all(consistency):
                raise WeeklyWorkforceProposalSnapshotMismatchError(
                    "existing snapshot does not match authoritative snapshot"
                )
            return

        conn.execute(
            """
            INSERT INTO weekly_planning_input_snapshots (
                organization_id, snapshot_id, period_start, period_end,
                operational_unit_identifier, operational_unit_name,
                policy_set_identifier, policy_set_version, fingerprint,
                created_at, payload_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                snapshot.organization_id,
                snapshot.snapshot_id,
                snapshot.period_start.isoformat(),
                snapshot.period_end.isoformat(),
                snapshot.operational_unit.external_identifier,
                snapshot.operational_unit.name,
                snapshot.policy_set_identifier,
                snapshot.policy_set_version,
                snapshot.fingerprint,
                snapshot.created_at.isoformat(),
                _canonical_json(snapshot),
            ),
        )

    @staticmethod
    def _insert_proposal(conn: Any, *, proposal: WeeklyWorkforceProposal) -> None:
        try:
            conn.execute(
                """
                INSERT INTO weekly_workforce_proposals (
                    organization_id, proposal_id, version, period_start,
                    period_end, operational_unit_identifier,
                    operational_unit_name, input_snapshot_id,
                    input_fingerprint, policy_set_identifier,
                    policy_set_version, status, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    proposal.organization_id,
                    proposal.proposal_id,
                    proposal.version,
                    proposal.period_start.isoformat(),
                    proposal.period_end.isoformat(),
                    proposal.operational_unit.external_identifier,
                    proposal.operational_unit.name,
                    proposal.input_snapshot_id,
                    proposal.input_fingerprint,
                    proposal.policy_set_identifier,
                    proposal.policy_set_version,
                    proposal.status.value,
                    proposal.created_at.isoformat(),
                ),
            )
        except sqlite3.IntegrityError as exc:
            raise WeeklyWorkforceProposalRevisionAlreadyExistsError(
                "proposal revision already exists"
            ) from exc

    @staticmethod
    def _insert_assignments(
        conn: Any,
        *,
        proposal: WeeklyWorkforceProposal,
        aggregate: ComposedWeeklyWorkforceProposal,
    ) -> None:
        for assignment in aggregate.assignments:
            conn.execute(
                """
                INSERT INTO weekly_workforce_proposal_assignments (
                    organization_id, proposal_id, proposal_version,
                    assignment_id, demand_trace_id, workforce_member_id,
                    operational_date, operational_unit_identifier,
                    operational_unit_name, time_window_identifier,
                    starts_at, ends_at, capability_or_workload,
                    shift_identifier, origin, status,
                    deterministic_priority, locked, reasons_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    proposal.organization_id,
                    proposal.proposal_id,
                    proposal.version,
                    assignment.assignment_id,
                    assignment.demand_trace_id,
                    assignment.workforce_member_id,
                    assignment.date.isoformat(),
                    assignment.operational_unit.external_identifier,
                    assignment.operational_unit.name,
                    assignment.time_window.external_identifier,
                    assignment.time_window.starts_at,
                    assignment.time_window.ends_at,
                    assignment.capability_or_workload,
                    assignment.shift_identifier,
                    assignment.origin.value,
                    assignment.status.value,
                    assignment.deterministic_priority,
                    int(assignment.locked),
                    _canonical_json(
                        [reason.model_dump(mode="json") for reason in assignment.reasons]
                    ),
                ),
            )

    @staticmethod
    def _insert_gaps(
        conn: Any,
        *,
        proposal: WeeklyWorkforceProposal,
        aggregate: ComposedWeeklyWorkforceProposal,
    ) -> None:
        for gap in aggregate.coverage_gaps:
            conn.execute(
                """
                INSERT INTO weekly_workforce_proposal_gaps (
                    organization_id, proposal_id, proposal_version,
                    demand_trace_id, operational_date,
                    operational_unit_identifier, operational_unit_name,
                    time_window_identifier, starts_at, ends_at,
                    capability_or_workload, required_quantity,
                    proposed_quantity, gap_quantity, reasons_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    proposal.organization_id,
                    proposal.proposal_id,
                    proposal.version,
                    gap.demand_trace_id,
                    gap.date.isoformat(),
                    gap.operational_unit.external_identifier,
                    gap.operational_unit.name,
                    gap.time_window.external_identifier,
                    gap.time_window.starts_at,
                    gap.time_window.ends_at,
                    gap.capability_or_workload,
                    gap.required_quantity,
                    gap.proposed_quantity,
                    gap.gap_quantity,
                    _canonical_json(
                        {
                            "reason": gap.reason.model_dump(mode="json"),
                            "excluded_candidate_categories": list(
                                gap.excluded_candidate_categories
                            ),
                        }
                    ),
                ),
            )

    @classmethod
    def _insert_explainability(
        cls,
        conn: Any,
        *,
        proposal: WeeklyWorkforceProposal,
        aggregate: ComposedWeeklyWorkforceProposal,
    ) -> None:
        cls._insert_artifacts(
            conn,
            proposal=proposal,
            artifact_type=_ELIGIBILITY,
            artifacts=aggregate.eligibility_decisions,
        )
        cls._insert_artifacts(
            conn,
            proposal=proposal,
            artifact_type=_PREFERENCE_SET,
            artifacts=aggregate.preference_sets,
        )
        cls._insert_artifacts(
            conn,
            proposal=proposal,
            artifact_type=_RANKED_CANDIDATE,
            artifacts=aggregate.ranked_candidates,
        )

    @staticmethod
    def _insert_artifacts(
        conn: Any,
        *,
        proposal: WeeklyWorkforceProposal,
        artifact_type: str,
        artifacts: Iterable[BaseModel],
    ) -> None:
        for ordinal, artifact in enumerate(artifacts):
            conn.execute(
                """
                INSERT INTO weekly_workforce_proposal_explainability (
                    organization_id, proposal_id, proposal_version,
                    demand_trace_id, artifact_type, ordinal,
                    workforce_member_id, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    proposal.organization_id,
                    proposal.proposal_id,
                    proposal.version,
                    artifact.demand_trace_id,
                    artifact_type,
                    ordinal,
                    artifact.workforce_member_id,
                    _canonical_json(artifact),
                ),
            )

    @classmethod
    def _load_revisions(
        cls,
        conn: Any,
        *,
        organization_id: str,
        proposal_id: str,
        version: int | None,
    ) -> tuple[ComposedWeeklyWorkforceProposal, ...]:
        version_clause = "" if version is None else " AND p.version = ?"
        parameters: tuple[object, ...] = (
            (organization_id, proposal_id)
            if version is None
            else (organization_id, proposal_id, version)
        )
        headers = conn.execute(
            f"""
            SELECT p.*
            FROM weekly_workforce_proposals p
            WHERE p.organization_id = ? AND p.proposal_id = ?
            {version_clause}
            ORDER BY p.version ASC
            """,
            parameters,
        ).fetchall()
        if not headers:
            return ()

        snapshots = conn.execute(
            f"""
            SELECT DISTINCT s.*
            FROM weekly_planning_input_snapshots s
            JOIN weekly_workforce_proposals p
              ON p.organization_id = s.organization_id
             AND p.input_snapshot_id = s.snapshot_id
             AND p.input_fingerprint = s.fingerprint
            WHERE p.organization_id = ? AND p.proposal_id = ?
            {version_clause}
            """,
            parameters,
        ).fetchall()
        assignments = conn.execute(
            f"""
            SELECT a.*
            FROM weekly_workforce_proposal_assignments a
            JOIN weekly_workforce_proposals p
              ON p.organization_id = a.organization_id
             AND p.proposal_id = a.proposal_id
             AND p.version = a.proposal_version
            WHERE p.organization_id = ? AND p.proposal_id = ?
            {version_clause}
            ORDER BY a.proposal_version ASC, a.operational_date ASC,
                     a.time_window_identifier ASC,
                     a.capability_or_workload ASC,
                     a.deterministic_priority ASC,
                     a.workforce_member_id ASC, a.assignment_id ASC
            """,
            parameters,
        ).fetchall()
        gaps = conn.execute(
            f"""
            SELECT g.*
            FROM weekly_workforce_proposal_gaps g
            JOIN weekly_workforce_proposals p
              ON p.organization_id = g.organization_id
             AND p.proposal_id = g.proposal_id
             AND p.version = g.proposal_version
            WHERE p.organization_id = ? AND p.proposal_id = ?
            {version_clause}
            ORDER BY g.proposal_version ASC, g.operational_date ASC,
                     g.time_window_identifier ASC,
                     g.capability_or_workload ASC, g.demand_trace_id ASC
            """,
            parameters,
        ).fetchall()
        explainability = conn.execute(
            f"""
            SELECT e.*
            FROM weekly_workforce_proposal_explainability e
            JOIN weekly_workforce_proposals p
              ON p.organization_id = e.organization_id
             AND p.proposal_id = e.proposal_id
             AND p.version = e.proposal_version
            WHERE p.organization_id = ? AND p.proposal_id = ?
            {version_clause}
            ORDER BY e.proposal_version ASC, e.artifact_type ASC,
                     e.ordinal ASC, e.demand_trace_id ASC
            """,
            parameters,
        ).fetchall()

        snapshot_by_key = {
            (row["snapshot_id"], row["fingerprint"]): _snapshot_from_row(row)
            for row in snapshots
        }
        assignments_by_version = cls._group_rows(
            assignments,
            factory=_assignment_from_row,
        )
        gaps_by_version = cls._group_rows(gaps, factory=_gap_from_row)
        artifact_groups: dict[int, dict[str, list[BaseModel]]] = {}
        for row in explainability:
            artifact_groups.setdefault(row["proposal_version"], {}).setdefault(
                row["artifact_type"], []
            ).append(_artifact_from_row(row))

        revisions: list[ComposedWeeklyWorkforceProposal] = []
        for header in headers:
            proposal = _proposal_from_row(header)
            artifacts = artifact_groups.get(proposal.version, {})
            aggregate = ComposedWeeklyWorkforceProposal(
                proposal=proposal,
                assignments=tuple(assignments_by_version.get(proposal.version, ())),
                coverage_gaps=tuple(gaps_by_version.get(proposal.version, ())),
                eligibility_decisions=tuple(artifacts.get(_ELIGIBILITY, ())),
                preference_sets=tuple(artifacts.get(_PREFERENCE_SET, ())),
                ranked_candidates=tuple(artifacts.get(_RANKED_CANDIDATE, ())),
            )
            snapshot_key = (
                proposal.input_snapshot_id,
                proposal.input_fingerprint,
            )
            try:
                snapshot = snapshot_by_key[snapshot_key]
            except KeyError as exc:
                raise WeeklyWorkforceProposalSnapshotMismatchError(
                    "proposal authoritative snapshot is missing"
                ) from exc
            validate_weekly_workforce_proposal_save_contract(
                organization_id=organization_id,
                snapshot=snapshot,
                aggregate=aggregate,
            )
            revisions.append(aggregate)
        return tuple(revisions)

    @staticmethod
    def _group_rows(
        rows: Iterable[Any],
        *,
        factory: Any,
    ) -> dict[int, list[BaseModel]]:
        grouped: dict[int, list[BaseModel]] = {}
        for row in rows:
            grouped.setdefault(row["proposal_version"], []).append(factory(row))
        return grouped
