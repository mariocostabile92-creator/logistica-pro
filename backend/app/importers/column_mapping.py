from app.schemas.import_schema import ColumnMappingSuggestion


def confirmed_fields_by_column(
    mapping: list[ColumnMappingSuggestion],
) -> dict[str, str]:
    return {
        item.source_column: item.target_field
        for item in mapping
        if item.target_field and not item.requires_confirmation
    }
