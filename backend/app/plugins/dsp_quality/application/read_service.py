import logging

from app.plugins.dsp_quality.application.read_models import (
    QualityLatestCounts,
    QualityLatestFocusArea,
    QualityLatestOverview,
    QualityLatestRevision,
    QualityLatestScorecard,
    QualityLatestSection,
    QualityLatestStandardSet,
)
from app.plugins.dsp_quality.infrastructure import read_repository


logger = logging.getLogger(__name__)


def get_scorecard(
    organization_id: str,
    scorecard_id: str | None = None,
) -> QualityLatestOverview:
    organization_id = organization_id.strip()
    if not organization_id:
        raise ValueError("Organization is required.")
    record = read_repository.scorecard_overview(organization_id, scorecard_id)
    if not record:
        return QualityLatestOverview(available=False)

    main = record["main"]
    if record["used_fallback"]:
        logger.warning(
            "DSP Quality active revision fallback used",
            extra={
                "organization_id": organization_id,
                "scorecard_id": main["scorecard_id"],
                "requested_revision_id": main["requested_active_revision_id"],
                "resolved_revision_id": main["revision_id"],
            },
        )

    return QualityLatestOverview(
        available=True,
        scorecard=QualityLatestScorecard(
            id=main["scorecard_id"],
            revision_id=main["revision_id"],
            dsp_identifier=main["dsp_identifier"],
            station=main["station"],
            reported_week=main["reported_week"],
            reported_year=main["reported_year"],
            geography=main["geography"],
            source_provider=main["source_provider"],
        ),
        revision=QualityLatestRevision(
            imported_at=main["imported_at"],
            imported_by=main["imported_by"],
            source_filename=main["source_filename"],
            detected_template_version=main["detected_template_version"],
            rank=main["rank"],
            rank_wow_declared=main["rank_wow_declared"],
            overall_score=main["overall_score"],
            overall_standing=main["overall_standing"],
            active_number=main["active_revision_number"],
            revision_count=main["revision_count"],
        ),
        sections=[
            QualityLatestSection(
                section_key=item["section_key"],
                label=item["section_label"],
                standing=item["standing"],
            )
            for item in record["sections"]
        ],
        focus_areas=[QualityLatestFocusArea(**item) for item in record["focus_areas"]],
        counts=QualityLatestCounts(**record["counts"]),
        standard_set=QualityLatestStandardSet(
            available=bool(main["standard_set_id"]),
            id=main["standard_set_id"],
            provider=main["standard_provider"],
            version=main["standard_version"],
            effective_from=main["standard_effective_from"],
            effective_to=main["standard_effective_to"],
        ),
    )


def get_latest_scorecard(organization_id: str) -> QualityLatestOverview:
    return get_scorecard(organization_id)
