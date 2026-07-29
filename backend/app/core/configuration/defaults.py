from app.core.configuration.models import (
    ConfigurationSection,
    ConfigurationValue,
    ConfigurationValueSource,
    ConfigurationVersion,
)


PLATFORM_DEFAULT_VERSION = ConfigurationVersion(
    number=0,
    created_at="2026-07-19T00:00:00Z",
    valid_from="2026-07-19T00:00:00Z",
    created_by="platform",
    note="Safe platform defaults for Configuration Engine v1.",
)

DEFAULT_AUTO_MAPPING_MIN_CONFIDENCE = 0.78
DEFAULT_REVIEW_MAPPING_MIN_CONFIDENCE = 0.58


def _section(
    key: str,
    values: dict[str, object],
) -> ConfigurationSection:
    return ConfigurationSection(
        key=key,
        values=[
            ConfigurationValue(
                key=value_key,
                value=value,
                source=ConfigurationValueSource.PLATFORM_DEFAULT,
            )
            for value_key, value in values.items()
        ],
    )


PLATFORM_DEFAULT_SECTIONS = [
    _section(
        "nomenclature",
        {
            "asset_label": "Asset",
            "human_resource_label": "Resource",
            "operational_unit_label": "Operational Unit",
            "task_label": "Task",
        },
    ),
    _section(
        "capabilities",
        {
            "asset": [],
            "human_resource": [],
        },
    ),
    _section(
        "asset_states",
        {
            "default": "available",
            "allowed": [
                "available",
                "unavailable",
                "maintenance",
                "reserve",
            ],
        },
    ),
    _section(
        "severities",
        {
            "default": "warning",
            "levels": ["info", "warning", "critical"],
        },
    ),
    _section(
        "readiness_levels",
        {
            "default": "green",
            "levels": ["green", "yellow", "red"],
        },
    ),
    _section(
        "reserve_policy",
        {
            "default_threshold": 1,
            "by_operational_unit": {},
        },
    ),
    _section(
        "priorities",
        {
            "default": "normal",
            "levels": ["low", "normal", "high"],
        },
    ),
    _section(
        "generic_mappings",
        {
            "auto_mapping_min_confidence": (
                DEFAULT_AUTO_MAPPING_MIN_CONFIDENCE
            ),
            "review_mapping_min_confidence": (
                DEFAULT_REVIEW_MAPPING_MIN_CONFIDENCE
            ),
            "mappings": {},
        },
    ),
]


def platform_default_sections() -> list[ConfigurationSection]:
    return [
        section.model_copy(deep=True)
        for section in PLATFORM_DEFAULT_SECTIONS
    ]
