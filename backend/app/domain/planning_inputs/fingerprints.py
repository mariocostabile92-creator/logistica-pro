import json
from hashlib import sha256
from typing import Any

from app.domain.planning_inputs.models import (
    PLANNING_INPUT_CONTRACT_VERSION,
    PlanningInputPayload,
    PlanningInputScope,
    PlanningInputSnapshot,
)


def _fingerprint(value: dict[str, Any]) -> str:
    canonical = json.dumps(
        value,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    )
    return sha256(canonical.encode("utf-8")).hexdigest()


def planning_input_fingerprint(
    scope: PlanningInputScope,
    payload: PlanningInputPayload,
) -> str:
    return _fingerprint(
        {
            "contract_version": PLANNING_INPUT_CONTRACT_VERSION,
            "scope": scope.model_dump(mode="json"),
            "payload": payload.model_dump(mode="json"),
        }
    )


def planning_input_envelope_fingerprint(
    scope: PlanningInputScope,
    snapshots: tuple[PlanningInputSnapshot, ...],
) -> str:
    versions = sorted(
        (
            {
                "input_type": item.contract.metadata.input_type.value,
                "source_reference": (
                    item.contract.metadata.source.source_reference
                ),
                "version": item.contract.metadata.version.value,
            }
            for item in snapshots
        ),
        key=lambda item: item["input_type"],
    )
    return _fingerprint(
        {
            "contract_version": PLANNING_INPUT_CONTRACT_VERSION,
            "scope": scope.model_dump(mode="json"),
            "snapshots": versions,
        }
    )
