from app.adapters.amazon.catalog import AmazonAdapterCatalog, load_catalog
from app.core.configuration.models import Configuration, ConfigurationScope
from app.core.configuration.service import get_current_configuration
from app.importers.adapter_contract import (
    AdapterConceptMapping,
    AdapterEventMapping,
    CoreConcept,
)


def _configured_mapping_aliases(
    configuration: Configuration,
    dataset_type: str,
) -> dict[str, list[str]]:
    for section in configuration.sections:
        if section.key != "generic_mappings":
            continue
        for item in section.values:
            if item.key != "mappings" or not isinstance(item.value, dict):
                continue
            dataset_mappings = item.value.get(dataset_type)
            if not isinstance(dataset_mappings, dict):
                return {}
            return {
                str(field): [
                    str(alias).strip()
                    for alias in aliases
                    if isinstance(alias, str) and alias.strip()
                ]
                for field, aliases in dataset_mappings.items()
                if isinstance(aliases, list)
            }
    return {}


def _merge_aliases(
    defaults: dict[str, list[str]],
    configured: dict[str, list[str]],
) -> dict[str, list[str]]:
    merged = {
        field: list(aliases)
        for field, aliases in defaults.items()
    }
    for field, aliases in configured.items():
        if field not in merged:
            continue
        known = {alias.casefold() for alias in merged[field]}
        for alias in aliases:
            if alias.casefold() not in known:
                merged[field].append(alias)
                known.add(alias.casefold())
    return merged


class AmazonAdapter:
    def __init__(self, catalog: AmazonAdapterCatalog | None = None):
        self._catalog = catalog or load_catalog()
        self.adapter_id = self._catalog.adapter_id
        self.contract_version = self._catalog.contract_version

    @staticmethod
    def _dataset_key(dataset_type: str) -> str:
        return "fleet" if dataset_type == "fleet" else "planning"

    def base_aliases_for(
        self,
        dataset_type: str,
    ) -> dict[str, list[str]]:
        dataset_key = self._dataset_key(dataset_type)
        return {
            field: list(aliases)
            for field, aliases in self._catalog.datasets[
                dataset_key
            ].items()
        }

    def aliases_for(
        self,
        dataset_type: str,
        organization_id: str = "default",
    ) -> dict[str, list[str]]:
        dataset_key = self._dataset_key(dataset_type)
        defaults = self.base_aliases_for(dataset_key)
        configuration = self._configuration_for(organization_id)
        configured = _configured_mapping_aliases(
            configuration,
            dataset_key,
        )
        return _merge_aliases(defaults, configured)

    def concept_mappings(self) -> list[AdapterConceptMapping]:
        return [
            mapping.model_copy(deep=True)
            for mapping in self._catalog.concept_mappings
        ]

    def event_mappings(self) -> list[AdapterEventMapping]:
        return [
            mapping.model_copy(deep=True)
            for mapping in self._catalog.event_mappings
        ]

    def recognized_operational_units(
        self,
        organization_id: str = "default",
    ) -> set[str]:
        return set(self._catalog.recognized_operational_units)

    def _configuration_for(
        self,
        organization_id: str,
    ) -> Configuration:
        return get_current_configuration(
            ConfigurationScope(
                organization_id=organization_id,
                adapter_id=self.adapter_id,
            )
        )

    def core_concept_for(self, external_term: str) -> CoreConcept | None:
        normalized = external_term.strip().casefold()
        for mapping in self._catalog.concept_mappings:
            if mapping.external_term.casefold() == normalized:
                return mapping.core_concept
        return None

    def event_mapping_for(
        self,
        external_event: str,
    ) -> AdapterEventMapping | None:
        normalized = external_event.strip().casefold()
        for mapping in self._catalog.event_mappings:
            if any(
                alias.casefold() == normalized
                for alias in mapping.aliases
            ):
                return mapping.model_copy(deep=True)
        return None

    def compatibility_event_for(
        self,
        external_event: str,
    ) -> str | None:
        mapping = self.event_mapping_for(external_event)
        return mapping.compatibility_event if mapping else None


AMAZON_ADAPTER = AmazonAdapter()
