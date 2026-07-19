from app.core.configuration.service import get_generic_mapping_thresholds
from app.schemas.import_schema import ColumnMappingSuggestion
from app.utils.text_normalizer import similarity


def suggest_mapping(
    columns: list[str],
    aliases: dict[str, list[str]],
    organization_id: str = "default",
) -> list[ColumnMappingSuggestion]:
    auto_mapping_threshold, review_mapping_threshold = (
        get_generic_mapping_thresholds(organization_id)
    )
    suggestions: list[ColumnMappingSuggestion] = []
    used_targets: set[str] = set()
    for column in columns:
        best_field = None
        best_score = 0.0
        for field, names in aliases.items():
            for alias in names:
                score = similarity(column, alias)
                if score > best_score:
                    best_score = score
                    best_field = field
        if best_field in used_targets and best_score < 1:
            best_field = None
            best_score = 0.0
        if best_field and best_score >= auto_mapping_threshold:
            used_targets.add(best_field)
            requires_confirmation = False
        elif best_score >= review_mapping_threshold:
            requires_confirmation = True
        else:
            best_field = None
            requires_confirmation = True
        suggestions.append(
            ColumnMappingSuggestion(
                source_column=column,
                target_field=best_field,
                confidence=round(best_score, 2),
                requires_confirmation=requires_confirmation,
            )
        )
    return suggestions
