from app.plugins.dsp_quality.application.attention_read_service import (
    ESCALATION_KEY,
    VOLUME_ONLY_KEYS,
    classify_driver_attention,
)
from app.plugins.dsp_quality.application.driver_history_models import (
    QualityDriverHistoryEntry,
    QualityDriverHistoryMetric,
    QualityDriverHistoryPeriod,
    QualityDriverHistoryReadModel,
    QualityDriverHistorySummary,
    QualityDriverHistoryTrend,
)
from app.plugins.dsp_quality.application.drivers_read_service import (
    DRIVER_METRIC_KEYS,
    build_driver_performance_row,
)
from app.plugins.dsp_quality.domain.metric_catalog import METRIC_DEFINITIONS_BY_KEY
from app.plugins.dsp_quality.infrastructure import driver_history_repository


_COMPARISON = {
    "improved": "IMPROVED",
    "worsened": "WORSENED",
    "unchanged": "UNCHANGED",
    "unknown": "NOT_COMPARABLE",
}


def _period_group(period: dict, observations: list[dict]) -> dict:
    return {
        "row_id": period["row_id"],
        "row_index": int(period["row_index"]),
        "transporter_external_id": period["transporter_external_id"],
        "mapping_status": period["resolved_mapping_status"],
        "workforce_member_id": period["resolved_workforce_member_id"],
        "workforce_display_name": period["workforce_display_name"],
        "metrics": {item["metric_key"]: item for item in observations},
    }


def _trend_model(key: str, state: dict) -> QualityDriverHistoryTrend:
    definition = METRIC_DEFINITIONS_BY_KEY[key]
    return QualityDriverHistoryTrend(
        metric_key=key,
        label=definition.canonical_label,
        direction=("NO_DIRECTION" if key in VOLUME_ONLY_KEYS else definition.direction.value),
        consecutive_worsening_comparisons=state["worsening"],
        consecutive_improving_comparisons=state["improving"],
        recurring=state["worsening"] >= 2,
        recovery=state["negative_sequence"] and state["improving"] >= 2,
    )


def get_driver_history(
    organization_id: str,
    transporter_external_id: str,
    *,
    scorecard_id: str | None = None,
    limit: int = 52,
) -> QualityDriverHistoryReadModel:
    organization_id = organization_id.strip()
    transporter_external_id = transporter_external_id.strip()
    if not transporter_external_id:
        raise ValueError("Transporter ID non valido.")

    snapshot = driver_history_repository.driver_history_snapshot(
        organization_id,
        transporter_external_id,
        scorecard_id=scorecard_id,
        limit=limit,
    )
    if not snapshot:
        raise LookupError("Contesto scorecard non trovato.")

    anchor = snapshot["anchor"]
    periods = sorted(
        snapshot["periods"],
        key=lambda item: (
            int(item["reported_year"]),
            int(item["reported_week"]),
            item["scorecard_id"],
        ),
    )
    if not periods:
        return QualityDriverHistoryReadModel(
            available=False,
            transporter_external_id=transporter_external_id,
            source_provider=anchor["source_provider"],
            dsp_identifier=anchor["dsp_identifier"],
            station=anchor["station"],
            anchor_scorecard_id=anchor["scorecard_id"],
            anchor_period=QualityDriverHistoryPeriod(
                year=int(anchor["reported_year"]),
                week=int(anchor["reported_week"]),
            ),
        )

    observations_by_row: dict[str, list[dict]] = {}
    for item in snapshot["observations"]:
        observations_by_row.setdefault(item["row_id"], []).append(item)

    trend_state = {
        key: {
            "worsening": 0,
            "improving": 0,
            "negative_sequence": False,
        }
        for key in DRIVER_METRIC_KEYS
        if key not in VOLUME_ONLY_KEYS
    }
    entries = []
    previous_group = None
    previous_period = None
    for period in periods:
        group = _period_group(
            period,
            observations_by_row.get(period["row_id"], []),
        )
        performance = build_driver_performance_row(
            group,
            previous_group,
            previous_period,
        )
        attention = classify_driver_attention(performance)
        metrics = []
        for metric in performance.metrics:
            comparison = _COMPARISON[
                metric.delta.direction_adjusted_improvement
            ]
            state = trend_state.get(metric.metric_key)
            if state is not None:
                if comparison == "WORSENED":
                    state["worsening"] += 1
                    state["improving"] = 0
                    if state["worsening"] >= 2:
                        state["negative_sequence"] = True
                elif comparison == "IMPROVED":
                    state["improving"] += 1
                    state["worsening"] = 0
                else:
                    state["worsening"] = 0
                    state["improving"] = 0
                recurring = state["worsening"] >= 2
                recovery = (
                    state["negative_sequence"] and state["improving"] >= 2
                )
                worsening = state["worsening"]
                improving = state["improving"]
            else:
                recurring = False
                recovery = False
                worsening = 0
                improving = 0
            metrics.append(QualityDriverHistoryMetric(
                metric_key=metric.metric_key,
                label=metric.label,
                unit=metric.unit,
                direction=metric.direction,
                value=metric.current,
                comparison=comparison,
                numeric_delta=metric.delta.numeric_delta,
                consecutive_worsening_comparisons=worsening,
                consecutive_improving_comparisons=improving,
                recurring=recurring,
                recovery=recovery,
            ))

        escalation = next(
            (item for item in metrics if item.metric_key == ESCALATION_KEY),
            None,
        )
        entries.append(QualityDriverHistoryEntry(
            scorecard_id=period["scorecard_id"],
            revision_id=period["revision_id"],
            year=int(period["reported_year"]),
            week=int(period["reported_week"]),
            imported_at=period["imported_at"],
            source_filename=period["source_filename"],
            weekly_status=attention.status,
            weekly_focus=attention.focus,
            reasons=attention.reasons,
            customer_escalations=(
                escalation.value.numeric_value if escalation else None
            ),
            metrics=metrics,
        ))
        previous_group = group
        previous_period = period

    current = next(
        (item for item in entries if item.scorecard_id == anchor["scorecard_id"]),
        entries[-1],
    )
    current_period_row = next(
        item for item in periods if item["scorecard_id"] == current.scorecard_id
    )
    trends = [
        _trend_model(key, state)
        for key, state in trend_state.items()
    ]
    first = entries[0]
    latest = entries[-1]
    return QualityDriverHistoryReadModel(
        available=True,
        transporter_external_id=transporter_external_id,
        workforce_member_id=current_period_row["resolved_workforce_member_id"],
        workforce_display_name=current_period_row["workforce_display_name"],
        mapping_status=current_period_row["resolved_mapping_status"],
        source_provider=anchor["source_provider"],
        dsp_identifier=anchor["dsp_identifier"],
        station=anchor["station"],
        anchor_scorecard_id=anchor["scorecard_id"],
        anchor_period=QualityDriverHistoryPeriod(
            year=int(anchor["reported_year"]),
            week=int(anchor["reported_week"]),
        ),
        summary=QualityDriverHistorySummary(
            weeks_available=len(entries),
            first_period=QualityDriverHistoryPeriod(
                year=first.year,
                week=first.week,
            ),
            latest_period=QualityDriverHistoryPeriod(
                year=latest.year,
                week=latest.week,
            ),
            current_status=current.weekly_status,
            current_focus=current.weekly_focus,
            recurring_worsening_metrics=[item for item in trends if item.recurring],
            recurring_improving_metrics=[
                item for item in trends
                if item.consecutive_improving_comparisons >= 2
            ],
            recent_customer_escalations=current.customer_escalations,
        ),
        metric_trends=trends,
        timeline=entries,
    )
