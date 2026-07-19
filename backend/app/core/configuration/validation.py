from app.core.configuration.models import (
    ConfigurationSection,
    ConfigurationValidationResult,
)


FORBIDDEN_SECRET_KEYS = {
    "api_key",
    "credential",
    "password",
    "secret",
    "token",
}


def _section_values(
    sections: list[ConfigurationSection],
) -> dict[str, dict[str, object]]:
    return {
        section.key: {
            item.key: item.value
            for item in section.values
        }
        for section in sections
    }


def _validate_default_in_levels(
    values: dict[str, object],
    section: str,
    errors: list[str],
) -> None:
    default = values.get("default")
    levels = values.get("levels")
    if not isinstance(levels, list) or not all(
        isinstance(item, str) and item
        for item in levels
    ):
        errors.append(f"{section}.levels deve essere una lista di stringhe.")
    elif default not in levels:
        errors.append(f"{section}.default deve essere incluso in levels.")


def validate_configuration_sections(
    sections: list[ConfigurationSection],
    fallback_sections: list[str] | None = None,
) -> ConfigurationValidationResult:
    errors: list[str] = []
    warnings: list[str] = []
    section_keys = [section.key for section in sections]
    if len(section_keys) != len(set(section_keys)):
        errors.append("Le chiavi delle sezioni devono essere uniche.")

    for section in sections:
        for item in section.values:
            if any(
                forbidden in item.key
                for forbidden in FORBIDDEN_SECRET_KEYS
            ):
                errors.append(
                    f"{section.key}.{item.key} non può contenere segreti."
                )

    values_by_section = _section_values(sections)
    asset_states = values_by_section.get("asset_states", {})
    allowed_states = asset_states.get("allowed")
    if not isinstance(allowed_states, list) or not all(
        isinstance(item, str) and item
        for item in allowed_states
    ):
        errors.append("asset_states.allowed deve essere una lista di stringhe.")
    elif asset_states.get("default") not in allowed_states:
        errors.append(
            "asset_states.default deve essere incluso in allowed."
        )

    for section_name in (
        "severities",
        "readiness_levels",
        "priorities",
    ):
        _validate_default_in_levels(
            values_by_section.get(section_name, {}),
            section_name,
            errors,
        )

    reserve_threshold = values_by_section.get(
        "reserve_policy",
        {},
    ).get("default_threshold")
    if (
        isinstance(reserve_threshold, bool)
        or not isinstance(reserve_threshold, int)
        or reserve_threshold < 0
    ):
        errors.append(
            "reserve_policy.default_threshold deve essere un intero >= 0."
        )

    mapping_values = values_by_section.get("generic_mappings", {})
    for key in (
        "auto_mapping_min_confidence",
        "review_mapping_min_confidence",
    ):
        value = mapping_values.get(key)
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not 0 <= float(value) <= 1
        ):
            errors.append(
                f"generic_mappings.{key} deve essere compreso tra 0 e 1."
            )
    auto_threshold = mapping_values.get("auto_mapping_min_confidence")
    review_threshold = mapping_values.get(
        "review_mapping_min_confidence"
    )
    if (
        isinstance(auto_threshold, (int, float))
        and not isinstance(auto_threshold, bool)
        and isinstance(review_threshold, (int, float))
        and not isinstance(review_threshold, bool)
        and review_threshold > auto_threshold
    ):
        errors.append(
            "La soglia di revisione non può superare quella automatica."
        )

    fallback = sorted(set(fallback_sections or []))
    if fallback:
        warnings.append(
            "Sono stati applicati default sicuri di piattaforma."
        )
    return ConfigurationValidationResult(
        valid=not errors,
        errors=errors,
        warnings=warnings,
        fallback_sections=fallback,
    )
