import hashlib
import json

from app.domain.workforce_auto_planning.operational_demand import (
    OperationalDemand,
)


def compute_operational_demand_trace_id(demand: OperationalDemand) -> str:
    payload = {
        "capability_or_workload": demand.capability_or_workload,
        "date": demand.date.isoformat(),
        "operational_unit_identifier": (
            demand.operational_unit.external_identifier
        ),
        "organization_id": demand.organization_id,
        "source": demand.source,
        "time_window_identifier": demand.time_window.external_identifier,
    }
    canonical_payload = json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(canonical_payload).hexdigest()
