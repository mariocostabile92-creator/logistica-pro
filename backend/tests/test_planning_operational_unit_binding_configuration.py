from pathlib import Path

import pytest

from app.core.configuration import repository
from app.core.configuration.models import (
    ConfigurationScope,
    ConfigurationSection,
    ConfigurationValue,
    ConfigurationValueSource,
)
from app.core.configuration.planning_operational_unit_binding_provider import (
    PLANNING_BINDING_ADAPTER_ID,
    PLANNING_BINDING_SECTION_KEY,
    PLANNING_BINDING_VALUE_KEY,
    ConfigurationPlanningOperationalUnitBindingProvider,
    PlanningOperationalUnitBindingAmbiguousError,
    PlanningOperationalUnitBindingMalformedError,
    PlanningOperationalUnitBindingNotFoundError,
    PlanningOperationalUnitBindingStorageError,
)
from app.core.configuration.repository import (
    ConfigurationStorageUnavailableError,
    StoredConfigurationInvalidError,
)
from app.domain.workforce_auto_planning import (
    PlanningOperationalUnitBindingProvider,
)


def _binding(
    *,
    context: str = "external-demand-source",
    unit: str = "unit-north",
    active: bool = True,
) -> dict[str, object]:
    return {
        "demand_source_context": context,
        "operational_unit": {
            "external_identifier": unit,
            "name": f"{unit} name",
        },
        "active": active,
    }


def _save(
    organization_id: str,
    bindings: object,
) -> None:
    repository.save_revision(
        scope=ConfigurationScope(
            organization_id=organization_id,
            adapter_id=PLANNING_BINDING_ADAPTER_ID,
        ),
        sections=[
            ConfigurationSection(
                key=PLANNING_BINDING_SECTION_KEY,
                values=[
                    ConfigurationValue(
                        key=PLANNING_BINDING_VALUE_KEY,
                        value=bindings,
                        source=ConfigurationValueSource.FUTURE_ADAPTER,
                    )
                ],
            )
        ],
        created_by="test-operator",
    )


def _provider() -> ConfigurationPlanningOperationalUnitBindingProvider:
    return ConfigurationPlanningOperationalUnitBindingProvider()


def test_resolves_the_single_active_binding_from_exact_scope():
    _save("org-a", [_binding()])

    result = _provider().resolve_binding(
        organization_id="org-a",
        demand_source_context="external-demand-source",
    )

    assert result.organization_id == "org-a"
    assert result.demand_source_context == "external-demand-source"
    assert result.operational_unit.external_identifier == "unit-north"
    assert result.binding_version == 1
    assert result.active is True


def test_concrete_resolver_implements_the_core_provider_protocol():
    assert isinstance(_provider(), PlanningOperationalUnitBindingProvider)


def test_missing_binding_fails_closed_without_fallback():
    _save("default", [_binding(unit="default-unit")])

    with pytest.raises(PlanningOperationalUnitBindingNotFoundError):
        _provider().resolve_binding(
            organization_id="org-a",
            demand_source_context="external-demand-source",
        )


def test_multiple_active_bindings_for_context_are_ambiguous():
    _save(
        "org-a",
        [_binding(unit="unit-a"), _binding(unit="unit-b")],
    )

    with pytest.raises(PlanningOperationalUnitBindingAmbiguousError):
        _provider().resolve_binding(
            organization_id="org-a",
            demand_source_context="external-demand-source",
        )


def test_inactive_bindings_are_ignored():
    _save(
        "org-a",
        [
            _binding(unit="inactive-unit", active=False),
            _binding(unit="active-unit"),
        ],
    )

    result = _provider().resolve_binding(
        organization_id="org-a",
        demand_source_context="external-demand-source",
    )

    assert result.operational_unit.external_identifier == "active-unit"


def test_only_inactive_binding_is_reported_as_missing():
    _save("org-a", [_binding(active=False)])

    with pytest.raises(PlanningOperationalUnitBindingNotFoundError):
        _provider().resolve_binding(
            organization_id="org-a",
            demand_source_context="external-demand-source",
        )


@pytest.mark.parametrize(
    "bindings",
    [
        {"not": "a-list"},
        ["not-an-object"],
        [{"demand_source_context": "external-demand-source", "active": True}],
        [
            {
                "demand_source_context": "external-demand-source",
                "operational_unit": {"external_identifier": "unit-a"},
                "active": "true",
            }
        ],
    ],
)
def test_malformed_configuration_is_rejected_deterministically(bindings):
    _save("org-a", bindings)

    with pytest.raises(PlanningOperationalUnitBindingMalformedError):
        _provider().resolve_binding(
            organization_id="org-a",
            demand_source_context="external-demand-source",
        )


def test_latest_configuration_revision_becomes_binding_version():
    _save("org-a", [_binding(unit="unit-v1")])
    _save("org-a", [_binding(unit="unit-v2")])

    result = _provider().resolve_binding(
        organization_id="org-a",
        demand_source_context="external-demand-source",
    )

    assert result.binding_version == 2
    assert result.operational_unit.external_identifier == "unit-v2"


def test_organization_isolation_for_same_context():
    _save("org-a", [_binding(unit="unit-a")])
    _save("org-b", [_binding(unit="unit-b")])

    first = _provider().resolve_binding(
        organization_id="org-a",
        demand_source_context="external-demand-source",
    )
    second = _provider().resolve_binding(
        organization_id="org-b",
        demand_source_context="external-demand-source",
    )

    assert first.operational_unit.external_identifier == "unit-a"
    assert second.operational_unit.external_identifier == "unit-b"


def test_loader_cannot_return_a_revision_from_another_scope():
    _save("org-b", [_binding(unit="unit-b")])
    wrong_revision = repository.get_latest_revision(
        ConfigurationScope(
            organization_id="org-b",
            adapter_id=PLANNING_BINDING_ADAPTER_ID,
        )
    )
    provider = ConfigurationPlanningOperationalUnitBindingProvider(
        revision_loader=lambda _scope: wrong_revision
    )

    with pytest.raises(PlanningOperationalUnitBindingMalformedError):
        provider.resolve_binding(
            organization_id="org-a",
            demand_source_context="external-demand-source",
        )


def test_stored_configuration_error_is_mapped_to_malformed_error():
    def fail(_scope):
        raise StoredConfigurationInvalidError("invalid")

    provider = ConfigurationPlanningOperationalUnitBindingProvider(fail)

    with pytest.raises(PlanningOperationalUnitBindingMalformedError):
        provider.resolve_binding(
            organization_id="org-a",
            demand_source_context="external-demand-source",
        )


def test_storage_unavailable_error_is_mapped_to_typed_storage_error():
    def fail(_scope):
        raise ConfigurationStorageUnavailableError("offline")

    provider = ConfigurationPlanningOperationalUnitBindingProvider(fail)

    with pytest.raises(PlanningOperationalUnitBindingStorageError):
        provider.resolve_binding(
            organization_id="org-a",
            demand_source_context="external-demand-source",
        )


def test_repeated_resolution_is_deterministic():
    _save("org-a", [_binding()])
    provider = _provider()

    first = provider.resolve_binding(
        organization_id="org-a",
        demand_source_context="external-demand-source",
    )
    second = provider.resolve_binding(
        organization_id="org-a",
        demand_source_context="external-demand-source",
    )

    assert first == second


def test_domain_contract_does_not_import_configuration_engine():
    domain_file = (
        Path(__file__).parents[1]
        / "app"
        / "domain"
        / "workforce_auto_planning"
        / "planning_operational_unit_binding.py"
    )
    source = domain_file.read_text(encoding="utf-8").lower()

    assert "app.core.configuration" not in source
    assert "repository" not in source
