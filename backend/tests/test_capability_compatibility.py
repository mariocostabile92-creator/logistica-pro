from pathlib import Path

import pytest
from pydantic import ValidationError

from app.domain.workforce_auto_planning import (
    AmbiguousCapabilityMappingError,
    CapabilityCompatibilityStatus,
    WorkloadCapabilityMapping,
    evaluate_capability_compatibility,
)


REQUIRED = "generic-workload"


def _mapping(
    *capabilities: str,
    workload_identifier: str = REQUIRED,
) -> WorkloadCapabilityMapping:
    return WorkloadCapabilityMapping(
        workload_identifier=workload_identifier,
        required_capabilities=capabilities,
    )


def _evaluate(
    *,
    candidate_capabilities: tuple[str, ...] = ("capability-a",),
    mappings: tuple[WorkloadCapabilityMapping, ...] = (),
):
    return evaluate_capability_compatibility(
        required_capability=REQUIRED,
        candidate_capabilities=candidate_capabilities,
        mappings=mappings,
    )


def test_explicit_mapping_and_candidate_capability_are_compatible():
    result = _evaluate(mappings=(_mapping("capability-a", "capability-b"),))
    evidence = {item.key: item.value for item in result.evidence}

    assert result.status == CapabilityCompatibilityStatus.COMPATIBLE
    assert result.required_capability == REQUIRED
    assert result.candidate_capabilities == ("capability-a",)
    assert result.reason.code == "explicit-capability-match"
    assert evidence["matched-candidate-capability-1"] == "capability-a"


def test_authoritative_mapping_without_match_is_incompatible():
    result = _evaluate(
        candidate_capabilities=("capability-c",),
        mappings=(_mapping("capability-a", "capability-b"),),
    )

    assert result.status == CapabilityCompatibilityStatus.INCOMPATIBLE
    assert result.reason.code == "no-explicit-capability-match"


def test_missing_authoritative_mapping_is_unknown():
    result = _evaluate(
        mappings=(
            _mapping(
                "capability-a",
                workload_identifier="different-workload",
            ),
        )
    )

    assert result.status == CapabilityCompatibilityStatus.UNKNOWN
    assert result.reason.code == "mapping-not-found"


def test_empty_candidate_capabilities_with_mapping_are_incompatible():
    result = _evaluate(
        candidate_capabilities=(),
        mappings=(_mapping("capability-a"),),
    )

    assert result.status == CapabilityCompatibilityStatus.INCOMPATIBLE


def test_empty_candidate_capabilities_without_mapping_are_unknown():
    result = _evaluate(candidate_capabilities=(), mappings=())

    assert result.status == CapabilityCompatibilityStatus.UNKNOWN


def test_identifiers_use_exact_matching_without_substrings():
    result = _evaluate(
        candidate_capabilities=("capability-a-extended",),
        mappings=(_mapping("capability-a"),),
    )

    assert result.status == CapabilityCompatibilityStatus.INCOMPATIBLE


def test_identifiers_use_exact_matching_without_implicit_casefold():
    result = _evaluate(
        candidate_capabilities=("CAPABILITY-A",),
        mappings=(_mapping("capability-a"),),
    )

    assert result.status == CapabilityCompatibilityStatus.INCOMPATIBLE


def test_mapping_lookup_is_exact_and_case_sensitive():
    result = _evaluate(
        mappings=(
            _mapping(
                "capability-a",
                workload_identifier="GENERIC-WORKLOAD",
            ),
        )
    )

    assert result.status == CapabilityCompatibilityStatus.UNKNOWN


def test_required_identifier_is_not_trimmed_into_a_mapping_match():
    result = evaluate_capability_compatibility(
        required_capability=" generic-workload ",
        candidate_capabilities=("capability-a",),
        mappings=(_mapping("capability-a"),),
    )

    assert result.status == CapabilityCompatibilityStatus.UNKNOWN
    assert result.required_capability == " generic-workload "


def test_ambiguous_authoritative_mapping_is_rejected():
    mappings = (
        _mapping("capability-a"),
        _mapping("capability-b"),
    )

    with pytest.raises(
        AmbiguousCapabilityMappingError,
        match="Multiple authoritative capability mappings",
    ):
        _evaluate(mappings=mappings)


def test_output_is_deterministic_and_inputs_are_not_mutated():
    candidate_capabilities = ("capability-b", "capability-a")
    mappings = (_mapping("capability-a", "capability-b"),)

    first = _evaluate(
        candidate_capabilities=candidate_capabilities,
        mappings=mappings,
    )
    second = _evaluate(
        candidate_capabilities=candidate_capabilities,
        mappings=mappings,
    )

    assert first == second
    assert candidate_capabilities == ("capability-b", "capability-a")
    assert mappings == (_mapping("capability-a", "capability-b"),)


def test_result_and_collections_are_immutable():
    result = _evaluate(mappings=(_mapping("capability-a"),))

    with pytest.raises(ValidationError):
        result.status = CapabilityCompatibilityStatus.UNKNOWN
    with pytest.raises(ValidationError):
        result.reason.code = "changed"
    with pytest.raises(TypeError):
        result.candidate_capabilities[0] = "changed"
    with pytest.raises(TypeError):
        result.evidence[0] = result.evidence[0]


def test_required_capability_is_mandatory():
    with pytest.raises(ValueError, match="required_capability cannot be empty"):
        evaluate_capability_compatibility(
            required_capability=" ",
            candidate_capabilities=(),
            mappings=(),
        )


def test_core_module_has_no_vertical_or_external_dependencies():
    source = (
        Path(__file__).resolve().parents[1]
        / "app"
        / "domain"
        / "workforce_auto_planning"
        / "capability_compatibility.py"
    ).read_text(encoding="utf-8").casefold()

    forbidden_fragments = (
        "amazon",
        "dsp",
        "fleet",
        "vehicle",
        "casefold",
        "startswith",
        "repository",
        "sqlalchemy",
        "fastapi",
        "shift_code",
    )
    assert all(fragment not in source for fragment in forbidden_fragments)
