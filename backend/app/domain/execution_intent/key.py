import hashlib
import json

from app.domain.execution_intent.models import (
    ExecutionIntentCommand,
    ExecutionIntentKey,
    ExecutionIntentScope,
)


def _sha256(payload: dict[str, object]) -> str:
    canonical = json.dumps(
        payload,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def execution_intent_key(scope: ExecutionIntentScope) -> ExecutionIntentKey:
    return ExecutionIntentKey(
        _sha256(
            {
                "contract": "execution-intent:v1",
                "organization_id": scope.organization_id,
                "operational_unit_id": scope.operational_unit_id,
                "planning_date": scope.planning_date.isoformat(),
                "timezone": scope.timezone,
                "publication_id": scope.publication_id,
                "publication_version": scope.publication_version,
                "execution_mode": scope.execution_mode.value,
            }
        )
    )


def execution_intent_payload_fingerprint(
    command: ExecutionIntentCommand,
    *,
    intent_key: ExecutionIntentKey,
) -> str:
    return _sha256(
        {
            "contract": "execution-intent-command:v1",
            "intent_key": str(intent_key),
            "publication_fingerprint": command.publication_fingerprint,
            "idempotency_key": command.idempotency_key,
            "expected_version": command.expected_version,
            "authority_decision_id": str(command.authority_decision_id),
            "fencing_token": command.fencing_token,
            "actor": command.actor,
        }
    )
