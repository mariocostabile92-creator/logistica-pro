import hashlib
import json

from app.domain.planning_confirmation.models import PlanningConfirmationScope
from app.domain.planning_drafts import PlanningDraft
from app.domain.planning_inputs import PlanningInputEnvelope


def planning_confirmation_fingerprint(
    *,
    scope: PlanningConfirmationScope,
    draft: PlanningDraft,
    envelope: PlanningInputEnvelope,
) -> str:
    payload = {
        "scope": {
            "organization_id": scope.organization_id,
            "operational_unit_id": (
                scope.operational_unit.external_identifier
            ),
            "planning_date": scope.planning_date.isoformat(),
        },
        "draft": {
            "draft_id": draft.draft_id,
            "version": draft.version.number,
            "name": draft.metadata.name,
            "note": draft.metadata.note,
        },
        "envelope": {
            "version": envelope.version.value,
            "fingerprint": envelope.fingerprint,
        },
    }
    encoded = json.dumps(
        payload,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
