from app.plugins.workforce.domain.consecutivity import ConsecutivityPolicy
from app.plugins.workforce.infrastructure import consecutivity_repository


def policy(organization_id: str) -> ConsecutivityPolicy:
    return consecutivity_repository.get_policy(organization_id)


def update_policy(
    organization_id: str,
    *,
    warning_threshold: int,
    rest_required_threshold: int,
    rest_break_days: int,
    actor: str,
) -> ConsecutivityPolicy:
    candidate = ConsecutivityPolicy(
        organization_id=organization_id,
        warning_threshold=warning_threshold,
        rest_required_threshold=rest_required_threshold,
        rest_break_days=rest_break_days,
        updated_by=actor,
        updated_at="1970-01-01T00:00:00+00:00",
    )
    return consecutivity_repository.save_policy(
        organization_id,
        candidate.model_dump(include={
            "warning_threshold", "rest_required_threshold", "rest_break_days"
        }),
        actor,
    )
