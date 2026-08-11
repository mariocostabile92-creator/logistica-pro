from collections.abc import Sequence
import hashlib
import json

from pydantic import BaseModel, Field

from app.plugins.workforce.domain.driver_shift_planning import DriverShiftPlanning


LEGACY_CANONICAL_PROVENANCE = "LEGACY_CANONICAL"


class LegacyCanonicalPublicationPreview(BaseModel):
    planning: DriverShiftPlanning
    rows_total: int = Field(ge=0)
    drivers_total: int = Field(ge=0)
    period_start: str
    period_end: str
    statuses_count: dict[str, int] = Field(default_factory=dict)
    provenance: str = LEGACY_CANONICAL_PROVENANCE
    ready_to_publish: bool = False
    fingerprint: str = Field(min_length=64, max_length=64)


def legacy_canonical_fingerprint(
    organization_id: str,
    planning_id: int,
    planning_version: int,
    period_start: str,
    period_end: str,
    rows: Sequence[dict[str, object]],
) -> str:
    """Fingerprint only the canonical values used by the published projection."""
    digest = hashlib.sha256()
    header = {
        "organization_id": organization_id,
        "planning_id": planning_id,
        "planning_version": planning_version,
        "period_start": period_start,
        "period_end": period_end,
        "provenance": LEGACY_CANONICAL_PROVENANCE,
    }
    digest.update(
        json.dumps(header, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
            "utf-8"
        )
    )
    for row in rows:
        values = (
            int(row["workforce_member_id"]),
            str(row["operational_date"]),
            str(row["status_code"]),
            bool(row["availability"]),
            row.get("shift_code"),
            row.get("start_time"),
            row.get("end_time"),
            row.get("notes"),
            row.get("source_reference"),
        )
        digest.update(b"\n")
        digest.update(
            json.dumps(values, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        )
    return digest.hexdigest()
