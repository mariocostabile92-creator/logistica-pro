import logging
from decimal import Decimal, InvalidOperation

from app.plugins.dsp_quality.application.metrics_read_models import (
    QualityLatestMetrics,
    QualityMetricCurrent,
    QualityMetricDelta,
    QualityMetricPrevious,
    QualityMetricReadItem,
    QualityMetricStandard,
    QualityMetricStandardSet,
    QualityMetricsPeriod,
    QualityMetricsSummary,
    QualityMetricStatus,
)
from app.plugins.dsp_quality.infrastructure import metrics_repository


logger = logging.getLogger(__name__)


def _decimal(value) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def _number(value) -> float | None:
    parsed = _decimal(value)
    return float(parsed) if parsed is not None else None


def _threshold_status(row: dict) -> QualityMetricStatus:
    current = _decimal(row["normalized_numeric_value"])
    if row["value_state"] != "PRESENT" or current is None:
        return QualityMetricStatus(
            target_status="NOT_EVALUABLE",
            minimum_status="NOT_EVALUABLE",
        )

    target = _decimal(row["target_value"])
    minimum = _decimal(row["minimum_value"])
    direction = row["standard_direction"] or row["direction"]
    if direction not in {"HIGHER_IS_BETTER", "LOWER_IS_BETTER"}:
        return QualityMetricStatus(
            target_status="NOT_EVALUABLE",
            minimum_status="NOT_EVALUABLE",
        )

    if target is None:
        target_status = "NO_STANDARD"
    elif direction == "HIGHER_IS_BETTER":
        target_status = "TARGET_MET" if current >= target else "BELOW_TARGET"
    else:
        target_status = "TARGET_MET" if current <= target else "BELOW_TARGET"

    if minimum is None:
        minimum_status = "NO_STANDARD"
    elif direction == "HIGHER_IS_BETTER":
        minimum_status = "TARGET_MET" if current >= minimum else "BELOW_MINIMUM"
    else:
        minimum_status = "TARGET_MET" if current <= minimum else "BELOW_MINIMUM"

    if target is None and minimum is None:
        target_status = minimum_status = "NO_STANDARD"
    return QualityMetricStatus(
        target_status=target_status,
        minimum_status=minimum_status,
    )


def _delta(current: dict, previous: dict | None) -> QualityMetricDelta:
    if not previous:
        return QualityMetricDelta()
    current_value = _decimal(current["normalized_numeric_value"])
    previous_value = _decimal(previous["normalized_numeric_value"])
    if (
        current["value_state"] != "PRESENT"
        or previous["value_state"] != "PRESENT"
        or current_value is None
        or previous_value is None
    ):
        return QualityMetricDelta()

    numeric_delta = current_value - previous_value
    if numeric_delta == 0:
        improvement = "unchanged"
    elif current["direction"] == "HIGHER_IS_BETTER":
        improvement = "improved" if numeric_delta > 0 else "worsened"
    elif current["direction"] == "LOWER_IS_BETTER":
        improvement = "improved" if numeric_delta < 0 else "worsened"
    else:
        improvement = "unknown"
    return QualityMetricDelta(
        numeric_delta=float(numeric_delta),
        direction_adjusted_improvement=improvement,
    )


def _effective_status(status: QualityMetricStatus) -> str:
    if status.minimum_status == "BELOW_MINIMUM":
        return "BELOW_MINIMUM"
    if status.target_status == "BELOW_TARGET":
        return "BELOW_TARGET"
    if status.target_status == "TARGET_MET":
        return "TARGET_MET"
    if status.target_status == "NOT_EVALUABLE":
        return "NOT_EVALUABLE"
    return "NO_STANDARD"


def get_metrics(
    organization_id: str,
    scorecard_id: str | None = None,
) -> QualityLatestMetrics:
    snapshot = metrics_repository.metrics_snapshot(organization_id, scorecard_id)
    if not snapshot:
        return QualityLatestMetrics(available=False)

    current_meta = snapshot["current"]
    previous_meta = snapshot["previous"]
    if snapshot["used_fallback"]:
        logger.warning(
            "DSP Quality metrics used revision fallback",
            extra={
                "organization_id": organization_id,
                "scorecard_id": current_meta["scorecard_id"],
                "requested_revision_id": current_meta["requested_active_revision_id"],
                "selected_revision_id": current_meta["revision_id"],
            },
        )

    previous_by_key = {
        row["metric_key"]: row for row in snapshot["previous_metrics"]
    }
    metrics = []
    categories = []
    target_met = attention = evaluatable = 0
    for row in snapshot["current_metrics"]:
        category = row["category"] or "other"
        if category not in categories:
            categories.append(category)
        previous_row = previous_by_key.get(row["metric_key"])
        status = _threshold_status(row)
        effective_status = _effective_status(status)
        if effective_status in {"TARGET_MET", "BELOW_TARGET", "BELOW_MINIMUM"}:
            evaluatable += 1
        if effective_status == "TARGET_MET":
            target_met += 1
        if effective_status in {"BELOW_TARGET", "BELOW_MINIMUM"}:
            attention += 1

        standard_set = None
        if row["standard_set_id"]:
            standard_set = QualityMetricStandardSet(
                id=row["standard_set_id"],
                provider=row["standard_provider"],
                detected_source_version=row["standard_version"],
                effective_from=row["standard_effective_from"],
                effective_to=row["standard_effective_to"],
            )
        metrics.append(QualityMetricReadItem(
            metric_key=row["metric_key"],
            label=row["canonical_label"],
            category=category,
            value_type=row["value_type"],
            unit=row["unit"],
            direction=row["direction"],
            current=QualityMetricCurrent(
                raw_value=row["raw_value"],
                numeric_value=_number(row["normalized_numeric_value"]),
                text_value=row["normalized_text_value"],
                value_state=row["value_state"],
                rating=row["rating"],
                compliance_state=row["compliance_state"],
            ),
            standard=QualityMetricStandard(
                target=_number(row["target_value"]),
                minimum=_number(row["minimum_value"]),
                raw_target=row["raw_target"],
                raw_minimum=row["raw_minimum"],
                standard_available=bool(
                    row["target_value"] is not None
                    or row["minimum_value"] is not None
                ),
                standard_set=standard_set,
            ),
            previous=QualityMetricPrevious(
                available=previous_row is not None,
                week=previous_meta["reported_week"] if previous_row else None,
                year=previous_meta["reported_year"] if previous_row else None,
                numeric_value=_number(previous_row["normalized_numeric_value"])
                if previous_row else None,
                text_value=previous_row["normalized_text_value"] if previous_row else None,
                rating=previous_row["rating"] if previous_row else None,
            ),
            delta=_delta(row, previous_row),
            status=status,
        ))

    return QualityLatestMetrics(
        available=True,
        metrics_available=bool(metrics),
        current_period=QualityMetricsPeriod(
            week=current_meta["reported_week"],
            year=current_meta["reported_year"],
        ),
        previous_period=QualityMetricsPeriod(
            week=previous_meta["reported_week"],
            year=previous_meta["reported_year"],
        ) if previous_meta else None,
        previous_available=bool(previous_meta),
        summary=QualityMetricsSummary(
            evaluatable=evaluatable,
            target_met=target_met,
            attention=attention,
        ),
        categories=categories,
        metrics=metrics,
    )


def get_latest_metrics(organization_id: str) -> QualityLatestMetrics:
    return get_metrics(organization_id)
