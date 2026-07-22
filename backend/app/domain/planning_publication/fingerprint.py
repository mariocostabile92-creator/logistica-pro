import hashlib
import json

from app.domain.planning_confirmation import PlanningConfirmation
from app.domain.planning_publication.models import PlanningPublicationScope


def planning_publication_fingerprint(
    *,
    scope: PlanningPublicationScope,
    confirmation: PlanningConfirmation,
    version: int,
) -> str:
    payload = {
        "scope": {
            "organization_id": scope.organization_id,
            "operational_unit_id": (
                scope.operational_unit.external_identifier
            ),
            "planning_date": scope.planning_date.isoformat(),
        },
        "publication_version": version,
        "confirmed_plan": {
            "confirmation_id": confirmation.confirmation_id,
            "version": confirmation.version,
            "fingerprint": confirmation.fingerprint,
        },
    }
    encoded = json.dumps(
        payload,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
