from decimal import Decimal

from app.plugins.dsp_quality.application.attention_read_service import get_attention
from app.plugins.dsp_quality.application.followup_models import (
    QualityFollowupCreateRequest,
    QualityFollowupCreateResult,
    QualityFollowupList,
    QualityFollowupPeriod,
    QualityFollowupReadModel,
    QualityFollowupReview,
    QualityFollowupSummary,
)
from app.plugins.dsp_quality.infrastructure import followup_repository


REVIEW_RESULTS = {"IMPROVED", "UNCHANGED", "WORSENED"}


def _number(value) -> float | None:
    if value is None:
        return None
    return float(Decimal(str(value)))


def _period_key(row: dict) -> tuple[int, int, str]:
    return (int(row["reported_year"]), int(row["reported_week"]), row["scorecard_id"])


def _candidate_scorecard(row: dict, scorecards: list[dict]) -> dict | None:
    matching = [
        item for item in scorecards
        if item["source_provider"] == row["source_provider"]
        and item["dsp_identifier"] == row["dsp_identifier"]
        and item["station"] == row["station"]
        and (
            int(item["reported_year"]),
            int(item["reported_week"]),
        ) > (
            int(row["created_from_year"]),
            int(row["created_from_week"]),
        )
    ]
    if row.get("target_review_scorecard_id"):
        return next(
            (item for item in matching if item["scorecard_id"] == row["target_review_scorecard_id"]),
            None,
        )
    return min(matching, key=_period_key) if matching else None


def _review_result(direction: str, baseline: float, current: float) -> str:
    if current == baseline:
        return "UNCHANGED"
    improved = current > baseline if direction == "HIGHER_IS_BETTER" else current < baseline
    return "IMPROVED" if improved else "WORSENED"


def _evaluate(row: dict, scorecards: list[dict], observations: list[dict]) -> tuple[QualityFollowupReview, dict | None]:
    baseline = _number(row["baseline_value"])
    candidate = _candidate_scorecard(row, scorecards)
    if not candidate:
        return QualityFollowupReview(
            state="WAITING_SCORECARD",
            message="In attesa della prima scorecard successiva disponibile.",
        ), None

    review_period = QualityFollowupPeriod(
        scorecard_id=candidate["scorecard_id"],
        year=int(candidate["reported_year"]),
        week=int(candidate["reported_week"]),
    )
    driver_rows = [
        item for item in observations
        if item["scorecard_id"] == candidate["scorecard_id"]
        and item["transporter_external_id"] == row["transporter_external_id"]
    ]
    update = {
        "id": row["id"],
        "organization_id": row["organization_id"],
        "transporter_external_id": row["transporter_external_id"],
        "metric_key": row["metric_key"],
        "scorecard_id": candidate["scorecard_id"],
        "target_already_set": bool(row.get("target_review_scorecard_id")),
    }
    if not driver_rows:
        return QualityFollowupReview(
            state="MISSING_DRIVER",
            period=review_period,
            message="Driver non presente nella scorecard successiva.",
        ), update
    observation = next(
        (item for item in driver_rows if item.get("metric_key") == row["metric_key"]),
        None,
    )
    current = _number(observation.get("normalized_numeric_value")) if observation else None
    if not observation or observation.get("value_state") != "PRESENT" or current is None:
        return QualityFollowupReview(
            state="MISSING_METRIC",
            period=review_period,
            message="Dati insufficienti per la verifica.",
        ), update

    result = row.get("review_result") or _review_result(
        row["baseline_direction"], baseline, current
    )
    update["result"] = result if row.get("review_result") is None else None
    review_period.value = current
    return QualityFollowupReview(
        state="COMPARABLE",
        result=result,
        period=review_period,
        delta=current - baseline,
        delta_unit=("pp" if row.get("metric_unit") == "percent" else row.get("metric_unit")),
        message={
            "IMPROVED": "La metrica è migliorata rispetto alla baseline.",
            "WORSENED": "La metrica è peggiorata rispetto alla baseline.",
            "UNCHANGED": "La metrica è invariata rispetto alla baseline.",
        }[result],
    ), (update if update.get("result") else None)


def _read_models(snapshot: dict) -> list[QualityFollowupReadModel]:
    updates = []
    output = []
    for row in snapshot["followups"]:
        review, update = _evaluate(row, snapshot["scorecards"], snapshot["observations"])
        if update and row["status"] != "CLOSED":
            updates.append(update)
        effective_status = row["status"]
        if effective_status != "CLOSED" and review.result in REVIEW_RESULTS:
            effective_status = review.result
        output.append(QualityFollowupReadModel(
            id=row["id"],
            transporter_external_id=row["transporter_external_id"],
            workforce_member_id=row["workforce_member_id"],
            driver_display_name=row["driver_display_name"],
            metric_key=row["metric_key"],
            metric_label=row["metric_label"],
            metric_unit=row["metric_unit"],
            baseline_direction=row["baseline_direction"],
            baseline_status=row["baseline_status"],
            baseline=QualityFollowupPeriod(
                scorecard_id=row["created_from_scorecard_id"],
                year=int(row["created_from_year"]),
                week=int(row["created_from_week"]),
                value=_number(row["baseline_value"]),
            ),
            note=row["note"],
            status=effective_status,
            created_by=row["created_by"],
            created_at=row["created_at"],
            review=review,
            closed_at=row["closed_at"],
            closed_by=row["closed_by"],
            close_note=row["close_note"],
        ))
    followup_repository.apply_review_updates(updates)
    return output


def _list(
    organization_id: str,
    *,
    followup_id: str | None = None,
    transporter_external_id: str | None = None,
    metric_key: str | None = None,
    status: str | None = None,
) -> QualityFollowupList:
    snapshot = followup_repository.followup_snapshot(
        organization_id,
        followup_id=followup_id,
        transporter_external_id=transporter_external_id,
        metric_key=metric_key,
    )
    items = _read_models(snapshot)
    if status:
        items = [item for item in items if item.status == status]
    return QualityFollowupList(
        items=items,
        summary=QualityFollowupSummary(
            open=sum(item.status != "CLOSED" for item in items),
            review_due=sum(
                item.status != "CLOSED" and item.review.state != "COMPARABLE"
                for item in items
            ),
            improved=sum(item.status == "IMPROVED" for item in items),
            worsened=sum(item.status == "WORSENED" for item in items),
            unchanged=sum(item.status == "UNCHANGED" for item in items),
            closed=sum(item.status == "CLOSED" for item in items),
        ),
    )


def list_followups(
    organization_id: str,
    *,
    status: str | None = None,
    transporter_external_id: str | None = None,
    metric_key: str | None = None,
) -> QualityFollowupList:
    if status and status not in {
        "OPEN", "REVIEW_DUE", "IMPROVED", "UNCHANGED", "WORSENED", "CLOSED"
    }:
        raise ValueError("Stato follow-up non valido.")
    return _list(
        organization_id,
        status=status,
        transporter_external_id=transporter_external_id,
        metric_key=metric_key,
    )


def get_followup(organization_id: str, followup_id: str) -> QualityFollowupReadModel:
    result = _list(organization_id, followup_id=followup_id)
    if not result.items:
        raise LookupError("Follow-up Quality non trovato.")
    return result.items[0]


def create_followup(
    organization_id: str,
    request: QualityFollowupCreateRequest,
    *,
    actor: str,
) -> QualityFollowupCreateResult:
    if request.metric_key == "delivered":
        raise ValueError("Delivered è una metrica di volume e non può generare follow-up Quality.")
    baseline = followup_repository.baseline_snapshot(
        organization_id,
        request.scorecard_id,
        request.transporter_external_id,
        request.metric_key,
    )
    if not baseline:
        raise LookupError("Driver o scorecard baseline non trovati.")
    if baseline.get("direction") not in {"HIGHER_IS_BETTER", "LOWER_IS_BETTER"}:
        raise ValueError("La metrica selezionata non ha una direzione Quality confrontabile.")
    if baseline.get("value_state") != "PRESENT" or baseline.get("normalized_numeric_value") is None:
        raise ValueError("La metrica baseline non contiene un valore numerico confrontabile.")

    duplicate = followup_repository.find_active_duplicate(
        organization_id,
        request.transporter_external_id,
        request.metric_key,
        request.scorecard_id,
    )
    if duplicate:
        return QualityFollowupCreateResult(
            created=False,
            item=get_followup(organization_id, duplicate["id"]),
        )

    attention = get_attention(organization_id, request.scorecard_id)
    baseline_driver = next(
        (
            item for item in attention.drivers
            if item.transporter_external_id == request.transporter_external_id
        ),
        None,
    )
    followup_id = followup_repository.create_followup({
        "organization_id": organization_id,
        "transporter_external_id": request.transporter_external_id,
        "workforce_member_id": baseline.get("workforce_member_id") or baseline.get("imported_workforce_member_id"),
        "created_from_scorecard_id": request.scorecard_id,
        "created_from_week": int(baseline["reported_week"]),
        "created_from_year": int(baseline["reported_year"]),
        "metric_key": request.metric_key,
        "baseline_value": str(baseline["normalized_numeric_value"]),
        "baseline_direction": baseline["direction"],
        "baseline_status": baseline_driver.status if baseline_driver else "SENZA_STORICO",
        "note": request.note,
    }, actor)
    if followup_id is None:
        duplicate = followup_repository.find_active_duplicate(
            organization_id,
            request.transporter_external_id,
            request.metric_key,
            request.scorecard_id,
        )
        if not duplicate:
            raise RuntimeError("Creazione follow-up non completata.")
        return QualityFollowupCreateResult(
            created=False,
            item=get_followup(organization_id, duplicate["id"]),
        )
    return QualityFollowupCreateResult(
        created=True,
        item=get_followup(organization_id, followup_id),
    )


def close_followup(
    organization_id: str,
    followup_id: str,
    *,
    actor: str,
    note: str | None = None,
) -> QualityFollowupReadModel:
    followup_repository.close_followup(
        organization_id,
        followup_id,
        actor=actor,
        note=note,
    )
    return get_followup(organization_id, followup_id)
