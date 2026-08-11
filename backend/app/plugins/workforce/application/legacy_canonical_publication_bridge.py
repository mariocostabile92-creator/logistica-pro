from collections import Counter

from app.plugins.workforce.domain.driver_shift_planning import (
    DriverShiftPlanningPublication,
    DriverShiftPlanningPublishBlockedError,
)
from app.plugins.workforce.domain.legacy_canonical_publication import (
    LEGACY_CANONICAL_PROVENANCE,
    LegacyCanonicalPublicationPreview,
    legacy_canonical_fingerprint,
)
from app.plugins.workforce.infrastructure import (
    legacy_canonical_publication_repository as repository,
)


def preview(
    organization_id: str,
    logical_planning_id: int,
) -> LegacyCanonicalPublicationPreview:
    planning, rows, _ = repository.read_preview_context(
        organization_id, logical_planning_id
    )
    if not rows:
        raise DriverShiftPlanningPublishBlockedError(
            "Nessun turno canonico disponibile nel periodo del planning."
        )
    fingerprint = legacy_canonical_fingerprint(
        organization_id,
        planning.id,
        planning.version,
        planning.period_start,
        planning.period_end,
        rows,
    )
    statuses = Counter(str(row["status_code"]) for row in rows)
    return LegacyCanonicalPublicationPreview(
        planning=planning,
        rows_total=len(rows),
        drivers_total=len({int(row["workforce_member_id"]) for row in rows}),
        period_start=planning.period_start,
        period_end=planning.period_end,
        statuses_count=dict(sorted(statuses.items())),
        provenance=LEGACY_CANONICAL_PROVENANCE,
        ready_to_publish=True,
        fingerprint=fingerprint,
    )


def publish(
    organization_id: str,
    logical_planning_id: int,
    expected_version: int,
    expected_fingerprint: str,
    *,
    actor: str = "local_operator",
) -> DriverShiftPlanningPublication:
    return repository.publish_legacy_projection(
        organization_id,
        logical_planning_id,
        expected_version,
        expected_fingerprint,
        actor.strip() or "local_operator",
    )
