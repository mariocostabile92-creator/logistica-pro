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
    _section(
        "workforce_statuses",
        {
            "default": "unknown",
            "allowed": [
                "available",
                "scheduled",
                "rest",
                "holiday",
                "sickness",
                "leave",
                "unavailable",
                "unknown",
            ],
            "external_mappings": {
                "available": ["available", "disponibile", "disp"],
                "scheduled": ["scheduled", "turno", "presente"],
                "rest": ["rest", "riposo", "r"],
                "holiday": ["holiday", "ferie", "f"],
                "sickness": ["sickness", "malattia", "m"],
                "leave": ["leave", "permesso", "p"],
                "unavailable": ["unavailable", "indisponibile"],
            },
            "available_statuses": ["available", "scheduled"],
        },
    ),
    _section(
        "workforce_shift_codes",
        {
            "mappings": {},
        },
    ),
    _section(
        "fleet_registry",
        {
            "availability_mappings": {
                "available": ["available", "disponibile", "operativo"],
                "unavailable": ["unavailable", "indisponibile", "bloccato"],
                "maintenance": ["maintenance", "officina", "guasto"],
                "reserve": ["reserve", "riserva", "muletto"],
            },
            "sensitive_aliases": [
                "pin",
                "password",
                "codice carta",
                "numero carta",
                "card number",
                "tessera carburante",
                "tessera q8",
            ],
            "column_mappings": {
                "rental_company": ["compagnia"],
                "replacement_vehicle": ["targa sostitutivo"],
                "workshop": ["offcina"],
            },
            "negative_issue_values": [
                "0",
                "no",
                "none",
                "nessuno",
                "nessun danno",
                "ok",
                "-",
                "false",
            ],
            "workshop_presence_means_maintenance": True,
            "damage_presence_means_unavailable": True,
            "infer_available_when_no_issue": True,
        },
    ),
]


def platform_default_sections() -> list[ConfigurationSection]:
    return [
        section.model_copy(deep=True)
        for section in PLATFORM_DEFAULT_SECTIONS
    ]
