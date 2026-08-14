from datetime import date

from app.core.database import db_session
from app.plugins.workforce.application import coverage_service
from app.plugins.workforce.domain.coverage import (
    DEFAULT_RESERVE_PERCENTAGE,
    DailyCoverageResponse,
    required_capacity_for,
)
from app.plugins.workforce.domain.manual_coverage import (
    ManualCoverageBucketError,
    ManualCoverageConflictError,
)
from app.plugins.workforce.infrastructure import (
    coverage_repository,
    manual_coverage_repository,
)
from app.utils.date_utils import utc_now_iso


SUPPORTED_BUCKETS = {
    ("NEXT_DAY", None),
    ("SAME_DAY", "A"),
    ("SAME_DAY", "B_C"),
}


def _normalize_bucket(item: dict[str, object]) -> dict[str, object]:
    cycle = str(item.get("cycle") or "").strip().upper()
    raw_segment = item.get("segment")
    segment = str(raw_segment).strip().upper() if raw_segment is not None else None
    if not segment:
        segment = None
    if (cycle, segment) not in SUPPORTED_BUCKETS:
        raise ManualCoverageBucketError(
            "Il bucket Coverage richiesto non e supportato."
        )
    forecast_routes = int(item["forecast_routes"])
    return {
        "cycle": cycle,
        "segment": segment,
        "forecast_routes": forecast_routes,
        "reserve_percentage": DEFAULT_RESERVE_PERCENTAGE,
        "required_capacity": required_capacity_for(
            forecast_routes, DEFAULT_RESERVE_PERCENTAGE
        ),
    }


def save_daily_forecast(
    *,
    organization_id: str,
    operational_date: str,
    requirements: list[dict[str, object]],
    expected_fingerprint: str,
    actor: str,
) -> DailyCoverageResponse:
    normalized_date = date.fromisoformat(operational_date).isoformat()
    normalized = [_normalize_bucket(item) for item in requirements]
    keys = [(item["cycle"], item["segment"]) for item in normalized]
    if len(keys) != len(set(keys)):
        raise ManualCoverageBucketError(
            "Lo stesso bucket Coverage non puo essere modificato due volte."
        )

    now = utc_now_iso()
    with db_session() as conn:
        current_requirements = (
            coverage_repository.list_current_requirements_in_connection(
                conn,
                organization_id,
                normalized_date,
                normalized_date,
            )
        )
        current_fingerprint = coverage_service.requirements_fingerprint(
            current_requirements,
            date_from=normalized_date,
            date_to=normalized_date,
        )
        if current_fingerprint != expected_fingerprint:
            raise ManualCoverageConflictError(
                "Il fabbisogno e cambiato. Aggiorna i dati e riprova."
            )
        current = {
            (item.operational_cycle, item.coverage_segment): item
            for item in current_requirements
        }
        manual_coverage_repository.save_manual_requirements(
            conn,
            organization_id=organization_id,
            operational_date=normalized_date,
            requirements=normalized,
            current=current,
            actor=actor,
            now=now,
        )

    return coverage_service.daily_coverage(
        organization_id, normalized_date, normalized_date
    )
