from pathlib import Path

import pytest
from pydantic import ValidationError

from app.domain.core_language import OperationalUnit
from app.domain.workforce_auto_planning import (
    PlanningOperationalUnitBinding,
    PlanningOperationalUnitBindingProvider,
)


UNIT_NORTH = OperationalUnit(external_identifier="unit-north", name="North hub")
UNIT_SOUTH = OperationalUnit(external_identifier="unit-south", name="South hub")


def _binding(**overrides) -> PlanningOperationalUnitBinding:
    values = {
        "organization_id": "org-1",
        "demand_source_context": "external-demand-source",
        "operational_unit": UNIT_NORTH,
        "binding_version": 1,
        "active": True,
    }
    values.update(overrides)
    return PlanningOperationalUnitBinding(**values)


class GenericBindingProvider:
    def __init__(self, binding: PlanningOperationalUnitBinding):
        self.binding = binding
        self.request: tuple[str, str] | None = None

    def resolve_binding(
        self,
        *,
        organization_id: str,
        demand_source_context: str,
    ) -> PlanningOperationalUnitBinding:
        self.request = (organization_id, demand_source_context)
        return self.binding


def test_valid_binding_can_be_created():
    binding = _binding()

    assert binding.organization_id == "org-1"
    assert binding.demand_source_context == "external-demand-source"
    assert binding.operational_unit == UNIT_NORTH
    assert binding.binding_version == 1
    assert binding.active is True


@pytest.mark.parametrize("organization_id", ["", "   "])
def test_organization_id_is_required(organization_id):
    with pytest.raises(ValidationError):
        _binding(organization_id=organization_id)


@pytest.mark.parametrize("demand_source_context", ["", "   "])
def test_demand_source_context_is_required(demand_source_context):
    with pytest.raises(ValidationError):
        _binding(demand_source_context=demand_source_context)


def test_operational_unit_is_required():
    with pytest.raises(ValidationError):
        _binding(operational_unit=None)


def test_operational_unit_identifier_cannot_be_blank():
    with pytest.raises(ValidationError, match="external_identifier cannot be empty"):
        _binding(operational_unit=OperationalUnit(external_identifier=" "))


@pytest.mark.parametrize("binding_version", [0, -1, True, 1.0, "1"])
def test_binding_version_must_be_a_strict_positive_integer(binding_version):
    with pytest.raises(ValidationError):
        _binding(binding_version=binding_version)


@pytest.mark.parametrize("active", [0, 1, "true", None])
def test_active_is_a_strict_boolean(active):
    with pytest.raises(ValidationError):
        _binding(active=active)


def test_binding_is_immutable():
    binding = _binding()

    with pytest.raises(ValidationError):
        binding.active = False


def test_different_source_contexts_produce_distinct_bindings():
    first = _binding(demand_source_context="source-one")
    second = _binding(demand_source_context="source-two")

    assert first != second


def test_same_context_can_target_different_units_in_different_organizations():
    first = _binding(organization_id="org-1", operational_unit=UNIT_NORTH)
    second = _binding(organization_id="org-2", operational_unit=UNIT_SOUTH)

    assert first.demand_source_context == second.demand_source_context
    assert first.organization_id != second.organization_id
    assert first.operational_unit != second.operational_unit


def test_provider_protocol_is_implementable_by_a_generic_adapter():
    binding = _binding()
    provider = GenericBindingProvider(binding)

    assert isinstance(provider, PlanningOperationalUnitBindingProvider)
    assert provider.resolve_binding(
        organization_id="org-1",
        demand_source_context="external-demand-source",
    ) is binding
    assert provider.request == ("org-1", "external-demand-source")


def test_core_contract_contains_no_vertical_or_runtime_dependencies():
    contract_file = (
        Path(__file__).parents[1]
        / "app"
        / "domain"
        / "workforce_auto_planning"
        / "planning_operational_unit_binding.py"
    )
    source = contract_file.read_text(encoding="utf-8").lower()

    forbidden_terms = (
        "amazon",
        "dsp",
        "coverage",
        "next_day",
        "same_day",
        "primary_station",
        "configuration engine",
        "repository",
        "database",
    )
    assert all(term not in source for term in forbidden_terms)
