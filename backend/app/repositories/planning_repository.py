import json
from enum import Enum
from typing import Any

from app.auth.tenant_context import current_organization_id
from app.core.database import db_session
from app.domain.planning_models import (
    GenerationMetadata,
    OperationalPlanning,
    PlanningBundle,
    PlanningConflict,
    PlanningSummary,
)
from app.repositories.assignment_repository import insert_assignment_in_session
from app.utils.date_utils import utc_now_iso


def _dump(value: Any) -> str:
    def default(item):
        if hasattr(item, "model_dump"):
            return item.model_dump(mode="json")
        if isinstance(item, Enum):
            return item.value
        raise TypeError(f"Tipo non serializzabile: {type(item).__name__}")

    return json.dumps(value, ensure_ascii=False, default=default)


def create_planning(bundle: PlanningBundle, actor: str = "system") -> PlanningBundle:
    planning = bundle.planning
    organization_id = current_organization_id()
    with db_session() as conn:
        cursor = conn.execute(
            """
            INSERT INTO plannings (
                organization_id, operation_date, station, source_planning_import_id,
                source_fleet_import_id, status, version, reserve_threshold,
                configuration, summary, conflicts, generation_metadata,
                created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                organization_id,
                planning.operation_date,
                planning.station,
                planning.source_planning_import_id,
                planning.source_fleet_import_id,
                planning.status.value,
                planning.version,
                planning.reserve_threshold,
                _dump(planning.configuration),
                _dump(bundle.summary),
                _dump(bundle.conflicts),
                _dump(bundle.generation_metadata),
                planning.created_at,
                planning.updated_at,
            ),
        )
        planning.id = int(cursor.lastrowid)
        for assignment in bundle.assignments:
            assignment.planning_id = planning.id
            assignment.id = insert_assignment_in_session(
                conn,
                planning.id,
                assignment,
            )
        conn.execute(
            """
            INSERT INTO planning_versions (
                planning_id, version, change_type, change_payload, actor, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                planning.id,
                planning.version,
                "generated",
                _dump(
                    {
                        "status": planning.status.value,
                        "summary": bundle.summary.model_dump(mode="json"),
                    }
                ),
                actor,
                utc_now_iso(),
            ),
        )
    return bundle


def _planning_from_row(row) -> OperationalPlanning:
    return OperationalPlanning(
        id=row["id"],
        operation_date=row["operation_date"],
        station=row["station"],
        source_planning_import_id=row["source_planning_import_id"],
        source_fleet_import_id=row["source_fleet_import_id"],
        status=row["status"],
        version=row["version"],
        reserve_threshold=row["reserve_threshold"],
        configuration=json.loads(row["configuration"]),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _record_from_row(row) -> dict[str, Any]:
    return {
        "planning": _planning_from_row(row),
        "summary": PlanningSummary.model_validate(json.loads(row["summary"])),
        "conflicts": [
            PlanningConflict.model_validate(item)
            for item in json.loads(row["conflicts"])
        ],
        "generation_metadata": GenerationMetadata.model_validate(
            json.loads(row["generation_metadata"])
        ),
    }


def get_planning_record(planning_id: int) -> dict[str, Any] | None:
    organization_id = current_organization_id()
    with db_session() as conn:
        row = conn.execute(
            "SELECT * FROM plannings WHERE id = ? AND organization_id = ?",
            (planning_id, organization_id),
        ).fetchone()
    return _record_from_row(row) if row else None


def get_latest_planning_record() -> dict[str, Any] | None:
    organization_id = current_organization_id()
    with db_session() as conn:
        row = conn.execute(
            """
            SELECT * FROM plannings
            WHERE organization_id = ?
            ORDER BY id DESC LIMIT 1
            """,
            (organization_id,),
        ).fetchone()
    return _record_from_row(row) if row else None


def update_planning_record(
    planning: OperationalPlanning,
    summary: PlanningSummary,
    conflicts: list[PlanningConflict],
    generation_metadata: GenerationMetadata,
) -> None:
    organization_id = current_organization_id()
    with db_session() as conn:
        conn.execute(
            """
            UPDATE plannings
            SET status = ?, version = ?, reserve_threshold = ?,
                configuration = ?, summary = ?, conflicts = ?,
                generation_metadata = ?, updated_at = ?
            WHERE id = ? AND organization_id = ?
            """,
            (
                planning.status.value,
                planning.version,
                planning.reserve_threshold,
                _dump(planning.configuration),
                _dump(summary),
                _dump(conflicts),
                _dump(generation_metadata),
                planning.updated_at,
                planning.id,
                organization_id,
            ),
        )


def save_version(
    planning_id: int,
    version: int,
    change_type: str,
    change_payload: dict[str, object],
    actor: str,
) -> None:
    with db_session() as conn:
        conn.execute(
            """
            INSERT INTO planning_versions (
                planning_id, version, change_type, change_payload, actor, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                planning_id,
                version,
                change_type,
                _dump(change_payload),
                actor,
                utc_now_iso(),
            ),
        )


def list_versions(planning_id: int) -> list[dict[str, object]]:
    organization_id = current_organization_id()
    with db_session() as conn:
        rows = conn.execute(
            """
            SELECT v.* FROM planning_versions v
            JOIN plannings p ON p.id=v.planning_id
            WHERE v.planning_id = ? AND p.organization_id = ?
            ORDER BY v.version ASC
            """,
            (planning_id, organization_id),
        ).fetchall()
    return [
        {
            "id": row["id"],
            "planning_id": row["planning_id"],
            "version": row["version"],
            "change_type": row["change_type"],
            "change_payload": json.loads(row["change_payload"]),
            "actor": row["actor"],
            "created_at": row["created_at"],
        }
        for row in rows
    ]
