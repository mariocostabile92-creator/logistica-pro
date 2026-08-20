import hashlib
import json
from collections.abc import Mapping, Sequence
from datetime import date as CalendarDate
from typing import Any

from pydantic import BaseModel

from app.domain.core_language import OperationalUnit
from app.domain.workforce_auto_planning.operational_demand import (
    OperationalDemand,
)
from app.domain.workforce_auto_planning.weekly_planning_input_snapshot import (
    WorkforceCandidateSnapshot,
)


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def _canonicalize(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return _canonicalize(value.model_dump(mode="json"))
    if isinstance(value, Mapping):
        return {
            str(key): _canonicalize(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        }
    if isinstance(value, (list, tuple, frozenset)):
        items = [_canonicalize(item) for item in value]
        return sorted(items, key=_canonical_json)
    return value


def _demand_sort_key(demand: OperationalDemand) -> tuple[str, ...]:
    canonical = _canonicalize(demand)
    return (
        demand.organization_id,
        demand.date.isoformat(),
        demand.operational_unit.external_identifier,
        demand.time_window.external_identifier,
        demand.capability_or_workload,
        demand.source,
        _canonical_json(canonical),
    )


def _candidate_sort_key(
    candidate: WorkforceCandidateSnapshot,
) -> tuple[str, ...]:
    canonical = _canonicalize(candidate)
    return (
        candidate.organization_id,
        candidate.workforce_member_id,
        _canonical_json(_canonicalize(candidate.applicable_contract_state)),
        _canonical_json(canonical),
    )


def compute_weekly_planning_input_fingerprint(
    *,
    organization_id: str,
    period_start: CalendarDate,
    period_end: CalendarDate,
    operational_unit: OperationalUnit,
    demands: Sequence[OperationalDemand],
    workforce_candidates: Sequence[WorkforceCandidateSnapshot],
    policy_set_identifier: str,
    policy_set_version: str,
) -> str:
    ordered_demands = sorted(demands, key=_demand_sort_key)
    ordered_candidates = sorted(workforce_candidates, key=_candidate_sort_key)
    payload = {
        "organization_id": organization_id,
        "period_start": period_start.isoformat(),
        "period_end": period_end.isoformat(),
        "operational_unit": _canonicalize(operational_unit),
        "demands": [_canonicalize(demand) for demand in ordered_demands],
        "workforce_candidates": [
            _canonicalize(candidate) for candidate in ordered_candidates
        ],
        "policy_set_identifier": policy_set_identifier,
        "policy_set_version": policy_set_version,
    }
    canonical_payload = _canonical_json(payload).encode("utf-8")
    return hashlib.sha256(canonical_payload).hexdigest()
