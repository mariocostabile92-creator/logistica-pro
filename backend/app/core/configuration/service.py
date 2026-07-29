from pydantic import ValidationError

from app.core.configuration import repository
from app.core.configuration.defaults import (
    DEFAULT_AUTO_MAPPING_MIN_CONFIDENCE,
    DEFAULT_REVIEW_MAPPING_MIN_CONFIDENCE,
    PLATFORM_DEFAULT_VERSION,
    platform_default_sections,
)
from app.core.configuration.models import (
    AppliedConfigurationVersion,
    Configuration,
    ConfigurationMetadata,
    ConfigurationRevision,
    ConfigurationScope,
    ConfigurationSection,
    ConfigurationValidationResult,
    ConfigurationValue,
    ConfigurationValueSource,
    ConfigurationVersion,
)
from app.core.configuration.repository import (
    ConfigurationStorageUnavailableError,
    StoredConfigurationInvalidError,
)
from app.core.configuration.validation import (
    validate_configuration_sections,
)


class ConfigurationValidationError(ValueError):
    def __init__(self, errors: list[str]):
        super().__init__("Configurazione non valida.")
        self.errors = errors


def _configuration_id(scope: ConfigurationScope) -> str:
    return ":".join(
        (
            scope.organization_id,
            scope.operational_unit_id or "global",
            scope.adapter_id or "core",
        )
    )


def _source_for_scope(
    scope: ConfigurationScope,
) -> ConfigurationValueSource:
    if scope.adapter_id:
        return ConfigurationValueSource.FUTURE_ADAPTER
    if scope.operational_unit_id:
        return ConfigurationValueSource.OPERATIONAL_UNIT
    return ConfigurationValueSource.ORGANIZATION


def _build_sections(
    raw_sections: list[dict[str, object]],
    source: ConfigurationValueSource,
) -> list[ConfigurationSection]:
    return [
        ConfigurationSection(
            key=str(section["key"]),
            values=[
                ConfigurationValue(
                    key=str(item["key"]),
                    value=item.get("value"),
                    source=source,
                )
                for item in section.get("values", [])
            ],
        )
        for section in raw_sections
    ]


def _merge_with_defaults(
    overrides: list[ConfigurationSection],
) -> tuple[list[ConfigurationSection], list[str]]:
    defaults = platform_default_sections()
    order = [section.key for section in defaults]
    sections_by_key = {
        section.key: {
            item.key: item.model_copy(deep=True)
            for item in section.values
        }
        for section in defaults
    }
    for section in overrides:
        if section.key not in sections_by_key:
            sections_by_key[section.key] = {}
            order.append(section.key)
        for item in section.values:
            sections_by_key[section.key][item.key] = item.model_copy(
                deep=True
            )

    merged = [
        ConfigurationSection(
            key=section_key,
            values=list(sections_by_key[section_key].values()),
        )
        for section_key in order
    ]
    fallback_sections = [
        section.key
        for section in merged
        if any(
            item.source is ConfigurationValueSource.PLATFORM_DEFAULT
            for item in section.values
        )
    ]
    return merged, fallback_sections


def _global_scope(scope: ConfigurationScope) -> ConfigurationScope:
    return ConfigurationScope(organization_id=scope.organization_id)


def _candidate_scopes(
    scope: ConfigurationScope,
) -> list[ConfigurationScope]:
    candidates = [_global_scope(scope)]
    if scope.operational_unit_id:
        candidates.append(
            ConfigurationScope(
                organization_id=scope.organization_id,
                operational_unit_id=scope.operational_unit_id,
            )
        )
    if scope.adapter_id:
        candidates.append(
            ConfigurationScope(
                organization_id=scope.organization_id,
                adapter_id=scope.adapter_id,
            )
        )
    if scope.operational_unit_id and scope.adapter_id:
        candidates.append(scope)
    return candidates


def _safe_revisions(
    scope: ConfigurationScope,
) -> tuple[list[ConfigurationRevision], list[str]]:
    warnings: list[str] = []
    revisions: list[ConfigurationRevision] = []
    try:
        for candidate in _candidate_scopes(scope):
            revision = repository.get_latest_revision(candidate)
            if revision:
                revisions.append(revision)
    except ConfigurationStorageUnavailableError:
        warnings.append(
            "Storage configurazioni non disponibile; applicati default sicuri."
        )
    except StoredConfigurationInvalidError:
        warnings.append(
            "Configurazione persistita non valida; applicati default sicuri."
        )
        return [], warnings
    if (
        (scope.operational_unit_id or scope.adapter_id)
        and (not revisions or revisions[-1].scope != scope)
    ):
        warnings.append(
            "Configurazione specifica non disponibile; applicato il livello "
            "di fallback più vicino."
        )
    return revisions, warnings


def get_current_configuration(
    scope: ConfigurationScope | None = None,
) -> Configuration:
    requested_scope = scope or ConfigurationScope()
    revisions, resolution_warnings = _safe_revisions(requested_scope)
    overrides = [
        section
        for revision in revisions
        for section in revision.sections
    ]
    sections, fallback_sections = _merge_with_defaults(overrides)
    validation = validate_configuration_sections(
        sections,
        fallback_sections,
    )
    if not validation.valid:
        sections = platform_default_sections()
        fallback_sections = [section.key for section in sections]
        validation = validate_configuration_sections(
            sections,
            fallback_sections,
        )
        resolution_warnings.append(
            "Configurazione effettiva non valida; applicati default sicuri."
        )

    version = (
        revisions[-1].version.model_copy(deep=True)
        if revisions
        else PLATFORM_DEFAULT_VERSION.model_copy(deep=True)
    )
    return Configuration(
        configuration_id=_configuration_id(requested_scope),
        version=version,
        metadata=ConfigurationMetadata(
            requested_scope=requested_scope,
            resolved_scope=revisions[-1].scope if revisions else None,
            fallback_used=bool(
                fallback_sections
                or resolution_warnings
                or not revisions
            ),
            fallback_sections=fallback_sections,
            applied_versions=[
                AppliedConfigurationVersion(
                    scope=revision.scope,
                    number=revision.version.number,
                )
                for revision in revisions
            ],
            validation_status="valid",
            warnings=[
                *resolution_warnings,
                *validation.warnings,
            ],
        ),
        sections=sections,
    )


def validate_configuration(
    raw_sections: list[dict[str, object]],
    scope: ConfigurationScope | None = None,
) -> ConfigurationValidationResult:
    effective_scope = scope or ConfigurationScope()
    try:
        sections = _build_sections(
            raw_sections,
            _source_for_scope(effective_scope),
        )
    except (KeyError, TypeError, ValidationError, ValueError) as exc:
        return ConfigurationValidationResult(
            valid=False,
            errors=[str(exc)],
        )
    section_keys = [section.key for section in sections]
    if len(section_keys) != len(set(section_keys)):
        return ConfigurationValidationResult(
            valid=False,
            errors=["Le chiavi delle sezioni devono essere uniche."],
        )
    merged, fallback_sections = _merge_with_defaults(sections)
    return validate_configuration_sections(
        merged,
        fallback_sections,
    )


def create_configuration_version(
    scope: ConfigurationScope,
    raw_sections: list[dict[str, object]],
    created_by: str,
    note: str | None = None,
    valid_from: str | None = None,
) -> Configuration:
    sections = _build_sections(
        raw_sections,
        _source_for_scope(scope),
    )
    section_keys = [section.key for section in sections]
    if len(section_keys) != len(set(section_keys)):
        raise ConfigurationValidationError(
            ["Le chiavi delle sezioni devono essere uniche."]
        )
    merged, fallback_sections = _merge_with_defaults(sections)
    validation = validate_configuration_sections(
        merged,
        fallback_sections,
    )
    if not validation.valid:
        raise ConfigurationValidationError(validation.errors)
    repository.save_revision(
        scope=scope,
        sections=sections,
        created_by=created_by,
        note=note,
        valid_from=valid_from,
    )
    return get_current_configuration(scope)


def list_configuration_versions(
    scope: ConfigurationScope,
) -> list[ConfigurationVersion]:
    try:
        return [
            revision.version
            for revision in repository.list_revisions(scope)
        ]
    except (
        ConfigurationStorageUnavailableError,
        StoredConfigurationInvalidError,
    ):
        return []


def _configuration_value(
    configuration: Configuration,
    section_key: str,
    value_key: str,
    fallback: object,
) -> object:
    for section in configuration.sections:
        if section.key != section_key:
            continue
        for item in section.values:
            if item.key == value_key:
                return item.value
    return fallback


def get_generic_mapping_thresholds(
    organization_id: str = "default",
) -> tuple[float, float]:
    configuration = get_current_configuration(
        ConfigurationScope(organization_id=organization_id)
    )
    auto_threshold = _configuration_value(
        configuration,
        "generic_mappings",
        "auto_mapping_min_confidence",
        DEFAULT_AUTO_MAPPING_MIN_CONFIDENCE,
    )
    review_threshold = _configuration_value(
        configuration,
        "generic_mappings",
        "review_mapping_min_confidence",
        DEFAULT_REVIEW_MAPPING_MIN_CONFIDENCE,
    )
    return float(auto_threshold), float(review_threshold)
