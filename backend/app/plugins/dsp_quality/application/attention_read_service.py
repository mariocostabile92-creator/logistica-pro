from app.plugins.dsp_quality.application.attention_read_models import (
    QualityAttentionFocus,
    QualityAttentionPeriod,
    QualityAttentionReadModel,
    QualityAttentionStatusCounts,
    QualityAttentionSummary,
    QualityDriverAttention,
    QualityDspAttention,
)
from app.plugins.dsp_quality.application.drivers_read_service import get_drivers
from app.plugins.dsp_quality.application.metrics_read_service import get_metrics


VOLUME_ONLY_KEYS = {"delivered"}
ESCALATION_KEY = "customer_escalations_count"
FOCUS_LABELS = {
    "delivery_completion_rate": "Delivery Completion",
    "photo_on_delivery": "Proof of Delivery",
    "contact_compliance": "Contact Compliance",
    "customer_delivery_feedback_dpmo": "Customer Delivery Feedback",
    ESCALATION_KEY: "Customer Escalations",
}
STATUS_ORDER = {
    "DA_ATTENZIONARE": 0,
    "DA_MIGLIORARE": 1,
    "IN_MIGLIORAMENTO": 2,
    "STABILE": 3,
    "SENZA_STORICO": 4,
}


def _display_name(row) -> str:
    return row.workforce_display_name or row.transporter_external_id


def _format_number(value: float | None) -> str:
    if value is None:
        return "non disponibile"
    return f"{value:g}"


def _focus(metric, reason: str) -> QualityAttentionFocus:
    return QualityAttentionFocus(
        metric_key=metric.metric_key,
        label=FOCUS_LABELS.get(metric.metric_key, metric.label),
        current=metric.current.numeric_value,
        previous=metric.previous.numeric_value,
        unit=metric.unit,
        direction=metric.delta.direction_adjusted_improvement,
        reason=reason,
    )


def classify_driver_attention(row) -> QualityDriverAttention:
    """Apply the exclusive, explainable Q10 driver classification rules."""
    comparable = [
        metric for metric in row.metrics
        if metric.metric_key not in VOLUME_ONLY_KEYS
        and metric.delta.direction_adjusted_improvement
        in {"improved", "worsened", "unchanged"}
    ]
    worsened = [
        metric for metric in comparable
        if metric.delta.direction_adjusted_improvement == "worsened"
    ]
    improved = [
        metric for metric in comparable
        if metric.delta.direction_adjusted_improvement == "improved"
    ]
    unchanged = [
        metric for metric in comparable
        if metric.delta.direction_adjusted_improvement == "unchanged"
    ]
    escalation_metric = next(
        (metric for metric in row.metrics if metric.metric_key == ESCALATION_KEY),
        None,
    )
    escalation_value = (
        escalation_metric.current.numeric_value if escalation_metric else None
    )
    escalation_present = escalation_value is not None and escalation_value > 0
    history_available = bool(comparable)

    if escalation_present or len(worsened) >= 2:
        status = "DA_ATTENZIONARE"
    elif not history_available:
        status = "SENZA_STORICO"
    elif len(worsened) == 1:
        status = "DA_MIGLIORARE"
    elif improved:
        status = "IN_MIGLIORAMENTO"
    else:
        status = "STABILE"

    reasons = []
    if escalation_present:
        reasons.append(
            f"{_format_number(escalation_value)} Customer Escalation nella scorecard corrente."
        )
    if worsened:
        reasons.append(
            f"{len(worsened)} metriche peggiorate rispetto alla precedente scorecard disponibile."
        )
    if status == "IN_MIGLIORAMENTO":
        reasons.append(
            f"{len(improved)} metriche migliorate e nessun peggioramento rilevato."
        )
    elif status == "STABILE":
        reasons.append("Nessun peggioramento o miglioramento significativo rilevato.")
    elif status == "SENZA_STORICO":
        reasons.append("Nessuna scorecard precedente comparabile per questo Transporter ID.")

    focus = []
    if escalation_present and escalation_metric:
        focus.append(_focus(
            escalation_metric,
            f"{_format_number(escalation_value)} escalation nella scorecard corrente.",
        ))
    focus_source = worsened if worsened else (improved if status == "IN_MIGLIORAMENTO" else [])
    for metric in focus_source:
        if metric.metric_key == ESCALATION_KEY and escalation_present:
            continue
        direction = "peggiorata" if metric in worsened else "migliorata"
        focus.append(_focus(
            metric,
            f"{_format_number(metric.previous.numeric_value)} → "
            f"{_format_number(metric.current.numeric_value)}; metrica {direction}.",
        ))
        if len(focus) == 3:
            break

    return QualityDriverAttention(
        row_id=row.row_id,
        transporter_external_id=row.transporter_external_id,
        workforce_member_id=row.workforce_member_id,
        display_name=_display_name(row),
        status=status,
        escalation_present=escalation_present,
        history_available=history_available,
        comparable_metrics=len(comparable),
        worsened_metrics=len(worsened),
        improved_metrics=len(improved),
        unchanged_metrics=len(unchanged),
        reasons=reasons,
        focus=focus,
    )


def _effective_metric_status(metric) -> str:
    if metric.status.minimum_status == "BELOW_MINIMUM":
        return "BELOW_MINIMUM"
    if metric.status.target_status == "BELOW_TARGET":
        return "BELOW_TARGET"
    return metric.status.target_status


def _dsp_attention(metric) -> QualityDspAttention | None:
    status = _effective_metric_status(metric)
    worsened = metric.delta.direction_adjusted_improvement == "worsened"
    if status not in {"BELOW_TARGET", "BELOW_MINIMUM"} and not worsened:
        return None
    reasons = []
    if status == "BELOW_MINIMUM":
        reasons.append("Valore sotto il minimo persistito per la scorecard.")
    elif status == "BELOW_TARGET":
        reasons.append("Valore sotto il target persistito per la scorecard.")
    if worsened:
        reasons.append("Andamento peggiorato rispetto alla precedente scorecard disponibile.")
    return QualityDspAttention(
        metric_key=metric.metric_key,
        label=metric.label,
        current=metric.current.numeric_value,
        previous=metric.previous.numeric_value,
        delta=metric.delta.numeric_delta,
        unit=metric.unit,
        direction=metric.delta.direction_adjusted_improvement,
        standard_target=metric.standard.target,
        standard_minimum=metric.standard.minimum,
        status=status,
        reason=" ".join(reasons),
    )


def get_attention(
    organization_id: str,
    scorecard_id: str | None = None,
) -> QualityAttentionReadModel:
    """Compose two fixed-size read snapshots; never queries per driver or metric."""
    drivers_model = get_drivers(organization_id, scorecard_id)
    metrics_model = get_metrics(organization_id, scorecard_id)
    if not drivers_model.available and not metrics_model.available:
        return QualityAttentionReadModel(available=False)

    drivers = [classify_driver_attention(row) for row in drivers_model.rows]
    drivers.sort(key=lambda item: (
        STATUS_ORDER[item.status],
        0 if item.escalation_present else 1,
        -item.worsened_metrics,
        item.display_name.casefold(),
        item.transporter_external_id.casefold(),
    ))
    dsp_signals = [
        signal for metric in metrics_model.metrics
        if (signal := _dsp_attention(metric)) is not None
    ]
    dsp_signals.sort(key=lambda item: (
        0 if item.status == "BELOW_MINIMUM" else 1,
        0 if item.direction == "worsened" else 1,
        item.label.casefold(),
    ))

    status_counts = QualityAttentionStatusCounts(
        da_attenzionare=sum(item.status == "DA_ATTENZIONARE" for item in drivers),
        da_migliorare=sum(item.status == "DA_MIGLIORARE" for item in drivers),
        in_miglioramento=sum(item.status == "IN_MIGLIORAMENTO" for item in drivers),
        stabile=sum(item.status == "STABILE" for item in drivers),
        senza_storico=sum(item.status == "SENZA_STORICO" for item in drivers),
    )
    return QualityAttentionReadModel(
        available=True,
        current_period=QualityAttentionPeriod(
            week=drivers_model.current_period.week or metrics_model.current_period.week,
            year=drivers_model.current_period.year or metrics_model.current_period.year,
        ),
        previous_period=(QualityAttentionPeriod(
            week=drivers_model.previous_period.week,
            year=drivers_model.previous_period.year,
        ) if drivers_model.previous_period else (
            QualityAttentionPeriod(
                week=metrics_model.previous_period.week,
                year=metrics_model.previous_period.year,
            ) if metrics_model.previous_period else None
        )),
        previous_available=drivers_model.previous_available or metrics_model.previous_available,
        summary=QualityAttentionSummary(
            total_drivers=len(drivers),
            dsp_metrics_attention_count=len(dsp_signals),
            drivers_attention_count=sum(
                item.status in {"DA_ATTENZIONARE", "DA_MIGLIORARE"}
                for item in drivers
            ),
            positive_trend_count=status_counts.in_miglioramento,
            drivers_without_history_count=status_counts.senza_storico,
            statuses=status_counts,
        ),
        dsp_signals=dsp_signals,
        drivers=drivers,
        driver_attention=[
            item for item in drivers
            if item.status in {"DA_ATTENZIONARE", "DA_MIGLIORARE"}
        ],
        positive_trends=[
            item for item in drivers if item.status == "IN_MIGLIORAMENTO"
        ],
    )


def get_latest_attention(organization_id: str) -> QualityAttentionReadModel:
    return get_attention(organization_id)
