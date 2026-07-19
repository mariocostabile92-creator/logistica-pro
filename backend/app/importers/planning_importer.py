from app.domain.normalized_models import NormalizedPlanningRow
from app.importers.column_mapping import confirmed_fields_by_column
from app.schemas.import_schema import ColumnMappingSuggestion
from app.utils.text_normalizer import compact_key, normalize_plate


def normalize_planning_rows(
    rows: list[dict[str, object]],
    mapping: list[ColumnMappingSuggestion],
) -> list[NormalizedPlanningRow]:
    field_by_column = confirmed_fields_by_column(mapping)
    normalized: list[NormalizedPlanningRow] = []
    for index, row in enumerate(rows, start=2):
        data: dict[str, object] = {}
        for column, value in row.items():
            field = field_by_column.get(column)
            if field:
                data[field] = value
        driver = str(data.get("driver_name") or "").strip() or None
        plate = normalize_plate(data.get("vehicle_plate")) or None
        normalized.append(
            NormalizedPlanningRow(
                row_number=index,
                driver_name=driver,
                driver_key=compact_key(driver) if driver else None,
                vehicle_plate=plate,
                station=str(data.get("station") or "").strip() or None,
                route=str(data.get("route") or "").strip() or None,
                cycle=str(data.get("cycle") or "").strip() or None,
                raw=row,
            )
        )
    return normalized
