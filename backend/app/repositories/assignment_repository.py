import json

from app.auth.tenant_context import current_organization_id
from app.core.database import db_session
from app.domain.assignment_models import Assignment


def _assignment_from_row(row) -> Assignment:
    return Assignment(
        id=row["id"],
        planning_id=row["planning_id"],
        operation_date=row["operation_date"],
        station=row["station"],
        route_id=row["route_id"],
        cycle_or_wave=row["cycle_or_wave"],
        driver_id=row["driver_id"],
        driver_name=row["driver_name"],
        vehicle_id=row["vehicle_id"],
        plate=row["plate"],
        assignment_status=row["assignment_status"],
        assignment_source=row["assignment_source"],
        confidence=row["confidence"],
        reasons=json.loads(row["reasons"]),
        data_used=json.loads(row["data_used"]),
        warnings=json.loads(row["warnings"]),
        alternatives=json.loads(row["alternatives"]),
        manual_override=bool(row["manual_override"]),
        confirmed=bool(row["confirmed"]),
        notes=row["notes"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def get_assignments(planning_id: int) -> list[Assignment]:
    organization_id = current_organization_id()
    with db_session() as conn:
        rows = conn.execute(
            """
            SELECT a.* FROM assignments a
            JOIN plannings p ON p.id=a.planning_id
            WHERE a.planning_id = ? AND p.organization_id = ?
            ORDER BY a.station, a.route_id, a.id
            """,
            (planning_id, organization_id),
        ).fetchall()
    return [_assignment_from_row(row) for row in rows]


def get_assignment(assignment_id: int) -> Assignment | None:
    organization_id = current_organization_id()
    with db_session() as conn:
        row = conn.execute(
            """
            SELECT a.* FROM assignments a
            JOIN plannings p ON p.id=a.planning_id
            WHERE a.id = ? AND p.organization_id = ?
            """,
            (assignment_id, organization_id),
        ).fetchone()
    return _assignment_from_row(row) if row else None


def update_assignment(assignment: Assignment) -> None:
    organization_id = current_organization_id()
    with db_session() as conn:
        conn.execute(
            """
            UPDATE assignments
            SET driver_id = ?, driver_name = ?, vehicle_id = ?, plate = ?,
                assignment_status = ?, assignment_source = ?, confidence = ?,
                reasons = ?, data_used = ?, warnings = ?, alternatives = ?,
                manual_override = ?, confirmed = ?, notes = ?, updated_at = ?
            WHERE id = ? AND planning_id IN (
                SELECT id FROM plannings WHERE organization_id = ?
            )
            """,
            (
                assignment.driver_id,
                assignment.driver_name,
                assignment.vehicle_id,
                assignment.plate,
                assignment.assignment_status.value,
                assignment.assignment_source.value,
                assignment.confidence,
                json.dumps(assignment.reasons, ensure_ascii=False),
                json.dumps(assignment.data_used, ensure_ascii=False),
                json.dumps(assignment.warnings, ensure_ascii=False),
                json.dumps(
                    [item.model_dump(mode="json") for item in assignment.alternatives],
                    ensure_ascii=False,
                ),
                int(assignment.manual_override),
                int(assignment.confirmed),
                assignment.notes,
                assignment.updated_at,
                assignment.id,
                organization_id,
            ),
        )


def update_assignments(assignments: list[Assignment]) -> None:
    for assignment in assignments:
        update_assignment(assignment)


def insert_assignment_in_session(
    conn,
    planning_id: int,
    assignment: Assignment,
) -> int:
    cursor = conn.execute(
        """
        INSERT INTO assignments (
            planning_id, operation_date, station, route_id, cycle_or_wave,
            driver_id, driver_name, vehicle_id, plate, assignment_status,
            assignment_source, confidence, reasons, data_used, warnings,
            alternatives, manual_override, confirmed, notes, created_at, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            planning_id,
            assignment.operation_date,
            assignment.station,
            assignment.route_id,
            assignment.cycle_or_wave,
            assignment.driver_id,
            assignment.driver_name,
            assignment.vehicle_id,
            assignment.plate,
            assignment.assignment_status.value,
            assignment.assignment_source.value,
            assignment.confidence,
            json.dumps(assignment.reasons, ensure_ascii=False),
            json.dumps(assignment.data_used, ensure_ascii=False),
            json.dumps(assignment.warnings, ensure_ascii=False),
            json.dumps(
                [item.model_dump(mode="json") for item in assignment.alternatives],
                ensure_ascii=False,
            ),
            int(assignment.manual_override),
            int(assignment.confirmed),
            assignment.notes,
            assignment.created_at,
            assignment.updated_at,
        ),
    )
    return int(cursor.lastrowid)


def insert_assignment(assignment: Assignment) -> Assignment:
    with db_session() as conn:
        assignment.id = insert_assignment_in_session(
            conn,
            assignment.planning_id,
            assignment,
        )
    return assignment
