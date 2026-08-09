from app.plugins.dsp_quality.application.history_models import (
    QualityScorecardHistory,
    QualityScorecardHistoryItem,
)
from app.plugins.dsp_quality.infrastructure import history_repository


def get_scorecard_history(organization_id: str) -> QualityScorecardHistory:
    organization_id = organization_id.strip()
    if not organization_id:
        raise ValueError("Organization is required.")
    return QualityScorecardHistory(items=[
        QualityScorecardHistoryItem.model_validate(item)
        for item in history_repository.list_history(organization_id)
    ])


def ensure_scorecard(organization_id: str, scorecard_id: str) -> None:
    if not history_repository.scorecard_exists(organization_id, scorecard_id):
        raise LookupError("Scorecard non disponibile.")

