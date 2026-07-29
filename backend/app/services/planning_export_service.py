import csv
import io

from app.schemas.planning_export_schema import PlanningExportRow
from app.services.planning_generation_service import get_planning_bundle


def export_planning_csv(planning_id: int) -> str:
    bundle = get_planning_bundle(planning_id)
    rows = [
        PlanningExportRow(
            operation_date=assignment.operation_date,
            station=assignment.station,
            route_id=assignment.route_id,
            cycle_or_wave=assignment.cycle_or_wave,
            driver_name=assignment.driver_name,
            plate=assignment.plate,
            assignment_status=assignment.assignment_status.value,
            assignment_source=assignment.assignment_source.value,
            manual_override=assignment.manual_override,
            warnings=" | ".join(assignment.warnings),
            notes=assignment.notes,
        )
        for assignment in bundle.assignments
    ]
    stream = io.StringIO(newline="")
    fieldnames = list(PlanningExportRow.model_fields)
    writer = csv.DictWriter(stream, fieldnames=fieldnames)
    writer.writeheader()
    for row in rows:
        writer.writerow(row.model_dump(mode="json"))
    return stream.getvalue()
