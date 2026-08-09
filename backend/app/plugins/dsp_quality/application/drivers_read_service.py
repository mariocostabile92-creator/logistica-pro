from collections import OrderedDict
from decimal import Decimal, InvalidOperation

from app.plugins.dsp_quality.application.drivers_read_models import (
    QualityDriverMetricDelta,
    QualityDriverMetricPrevious,
    QualityDriverMetricReadItem,
    QualityDriverMetricValue,
    QualityDriverPerformanceRow,
    QualityDriversPeriod,
    QualityDriversSummary,
    QualityLatestDrivers,
)
from app.plugins.dsp_quality.domain.metric_catalog import METRIC_DEFINITIONS_BY_KEY
from app.plugins.dsp_quality.infrastructure import drivers_repository


DRIVER_METRIC_KEYS = drivers_repository.TRANSPORTER_METRIC_KEYS


def _number(value) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(Decimal(str(value)))
    except (InvalidOperation, ValueError):
        return None


def _group_rows(rows: list[dict]) -> OrderedDict[str, dict]:
    grouped: OrderedDict[str, dict] = OrderedDict()
    for row in rows:
        group = grouped.setdefault(row["row_id"], {
            "row_id": row["row_id"],
            "row_index": int(row["row_index"]),
            "transporter_external_id": row["transporter_external_id"],
            "mapping_status": row["resolved_mapping_status"],
            "workforce_member_id": row["resolved_workforce_member_id"],
            "workforce_display_name": row["workforce_display_name"],
            "metrics": {},
        })
        if row["metric_key"]:
            group["metrics"][row["metric_key"]] = row
    return grouped


def _metric_value(row: dict | None) -> QualityDriverMetricValue:
    if not row:
        return QualityDriverMetricValue()
    return QualityDriverMetricValue(
        raw_value=row["raw_value"],
        numeric_value=_number(row["normalized_numeric_value"]),
        text_value=row["normalized_text_value"],
        value_state=row["value_state"] or "MISSING",
    )


def _previous_value(row: dict | None, period: dict | None) -> QualityDriverMetricPrevious:
    if not row:
        return QualityDriverMetricPrevious()
    return QualityDriverMetricPrevious(
        available=True,
        week=int(period["reported_week"]) if period else None,
        year=int(period["reported_year"]) if period else None,
        raw_value=row["raw_value"],
        numeric_value=_number(row["normalized_numeric_value"]),
        text_value=row["normalized_text_value"],
        value_state=row["value_state"] or "MISSING",
    )


def _direction(key: str, row: dict | None) -> str:
    if key == "delivered":
        return "NO_DIRECTION"
    if row and row.get("direction") in {"HIGHER_IS_BETTER", "LOWER_IS_BETTER"}:
        return row["direction"]
    definition = METRIC_DEFINITIONS_BY_KEY[key]
    return definition.direction.value


def _delta(
    current: QualityDriverMetricValue,
    previous: QualityDriverMetricPrevious,
    direction: str,
) -> QualityDriverMetricDelta:
    if (
        current.value_state != "PRESENT"
        or previous.value_state != "PRESENT"
        or current.numeric_value is None
        or previous.numeric_value is None
    ):
        return QualityDriverMetricDelta()
    numeric_delta = current.numeric_value - previous.numeric_value
    if direction not in {"HIGHER_IS_BETTER", "LOWER_IS_BETTER"}:
        improvement = "unknown"
    elif numeric_delta == 0:
        improvement = "unchanged"
    elif direction == "HIGHER_IS_BETTER":
        improvement = "improved" if numeric_delta > 0 else "worsened"
    else:
        improvement = "improved" if numeric_delta < 0 else "worsened"
    return QualityDriverMetricDelta(
        numeric_delta=round(numeric_delta, 6),
        direction_adjusted_improvement=improvement,
    )


def _metric_item(
    key: str,
    current_row: dict | None,
    previous_row: dict | None,
    previous_period: dict | None,
) -> QualityDriverMetricReadItem:
    definition = METRIC_DEFINITIONS_BY_KEY[key]
    current = _metric_value(current_row)
    previous = _previous_value(previous_row, previous_period)
    direction = _direction(key, current_row)
    return QualityDriverMetricReadItem(
        metric_key=key,
        label=definition.canonical_label,
        value_type=definition.value_type.value,
        unit=definition.unit,
        direction=direction,
        current=current,
        previous=previous,
        delta=_delta(current, previous, direction),
    )


def get_latest_drivers(organization_id: str) -> QualityLatestDrivers:
    snapshot = drivers_repository.latest_drivers_snapshot(organization_id.strip())
    if not snapshot:
        return QualityLatestDrivers(available=False)

    current = snapshot["current"]
    previous = snapshot["previous"]
    current_groups = _group_rows(snapshot["current_rows"])
    previous_groups = _group_rows(snapshot["previous_rows"])
    previous_by_external_id = {
        row["transporter_external_id"]: row for row in previous_groups.values()
    }
    rows = []
    for row in current_groups.values():
        previous_row = previous_by_external_id.get(row["transporter_external_id"])
        mapping_status = row["mapping_status"]
        workforce_member_id = row["workforce_member_id"]
        display_name = row["workforce_display_name"]
        if mapping_status == "MATCHED" and (not workforce_member_id or not display_name):
            mapping_status = "AMBIGUOUS"
            workforce_member_id = None
            display_name = None
        rows.append(QualityDriverPerformanceRow(
            row_id=row["row_id"],
            row_index=row["row_index"],
            transporter_external_id=row["transporter_external_id"],
            mapping_status=mapping_status,
            workforce_member_id=workforce_member_id if mapping_status == "MATCHED" else None,
            workforce_display_name=display_name if mapping_status == "MATCHED" else None,
            metrics=[
                _metric_item(
                    key,
                    row["metrics"].get(key),
                    previous_row["metrics"].get(key) if previous_row else None,
                    previous,
                )
                for key in DRIVER_METRIC_KEYS
            ],
        ))

    summary = QualityDriversSummary(
        total=len(rows),
        matched=sum(row.mapping_status == "MATCHED" for row in rows),
        unmapped=sum(row.mapping_status == "UNMAPPED" for row in rows),
        ambiguous=sum(row.mapping_status == "AMBIGUOUS" for row in rows),
    )
    return QualityLatestDrivers(
        available=True,
        drivers_available=bool(rows),
        current_period=QualityDriversPeriod(
            week=int(current["reported_week"]),
            year=int(current["reported_year"]),
        ),
        previous_period=QualityDriversPeriod(
            week=int(previous["reported_week"]),
            year=int(previous["reported_year"]),
        ) if previous else None,
        previous_available=bool(previous),
        summary=summary,
        rows=rows,
    )
