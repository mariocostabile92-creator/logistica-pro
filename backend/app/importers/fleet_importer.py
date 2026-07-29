from app.domain.normalized_models import NormalizedFleetRow
from app.importers.column_mapping import confirmed_fields_by_column
from app.schemas.import_schema import ColumnMappingSuggestion
from app.utils.text_normalizer import compact_key, normalize_plate


def normalize_fleet_rows(
    rows: list[dict[str, object]],
    mapping: list[ColumnMappingSuggestion],
) -> list[NormalizedFleetRow]:
    field_by_column = confirmed_fields_by_column(mapping)
    normalized: list[NormalizedFleetRow] = []
    for index, row in enumerate(rows, start=2):
        data: dict[str, object] = {}
        for column, value in row.items():
            field = field_by_column.get(column)
            if field:
                data[field] = value
        driver = str(data.get("driver_name") or "").strip() or None
        second_driver = str(data.get("second_driver_name") or "").strip() or None
        normalized.append(
            NormalizedFleetRow(
                row_number=index,
                vehicle_plate=normalize_plate(data.get("vehicle_plate")) or None,
                driver_name=driver,
                driver_key=compact_key(driver) if driver else None,
                second_driver_name=second_driver,
                second_driver_key=compact_key(second_driver) if second_driver else None,
                status=str(data.get("status") or "").strip() or None,
                station=str(data.get("station") or "").strip() or None,
                workshop=str(data.get("workshop") or "").strip() or None,
                notes=str(data.get("notes") or "").strip() or None,
                key_available=str(data.get("key_available") or "").strip() or None,
                fuel_card=str(data.get("fuel_card") or "").strip() or None,
                vehicle_model=str(data.get("vehicle_model") or "").strip() or None,
                expirations=str(data.get("expirations") or "").strip() or None,
                raw=row,
            )
        )
    return normalized
