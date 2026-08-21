from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

from app.domain.workforce_auto_planning.constraint_evaluation import (
    ConstraintEvidence,
)
from app.domain.workforce_auto_planning.planning_policy import (
    WorkloadCapabilityMapping,
)


class CapabilityCompatibilityStatus(str, Enum):
    COMPATIBLE = "COMPATIBLE"
    INCOMPATIBLE = "INCOMPATIBLE"
    UNKNOWN = "UNKNOWN"


class CapabilityCompatibilityReason(BaseModel):
    model_config = ConfigDict(frozen=True, str_strip_whitespace=True)

    code: str = Field(min_length=1)
    message: str = Field(min_length=1)


class CapabilityCompatibilityEvaluation(BaseModel):
    model_config = ConfigDict(frozen=True)

    status: CapabilityCompatibilityStatus
    required_capability: str = Field(min_length=1)
    candidate_capabilities: tuple[str, ...] = Field(default_factory=tuple)
    reason: CapabilityCompatibilityReason
    evidence: tuple[ConstraintEvidence, ...] = Field(default_factory=tuple)


class AmbiguousCapabilityMappingError(ValueError):
    pass


def evaluate_capability_compatibility(
    *,
    required_capability: str,
    candidate_capabilities: tuple[str, ...],
    mappings: tuple[WorkloadCapabilityMapping, ...],
) -> CapabilityCompatibilityEvaluation:
    if (
        not isinstance(required_capability, str)
        or not required_capability.strip()
    ):
        raise ValueError("required_capability cannot be empty")
    required = required_capability
    authoritative_mappings = tuple(
        mapping
        for mapping in mappings
        if mapping.workload_identifier == required
    )
    if len(authoritative_mappings) > 1:
        raise AmbiguousCapabilityMappingError(
            "Multiple authoritative capability mappings were found."
        )

    evidence = [
        ConstraintEvidence(
            key="authoritative-mapping-count",
            value=len(authoritative_mappings),
        ),
        ConstraintEvidence(
            key="candidate-capability-count",
            value=len(candidate_capabilities),
        ),
    ]
    if not authoritative_mappings:
        return CapabilityCompatibilityEvaluation(
            status=CapabilityCompatibilityStatus.UNKNOWN,
            required_capability=required,
            candidate_capabilities=candidate_capabilities,
            reason=CapabilityCompatibilityReason(
                code="mapping-not-found",
                message=(
                    "No authoritative capability mapping is available."
                ),
            ),
            evidence=tuple(evidence),
        )

    mapping = authoritative_mappings[0]
    evidence.extend(
        ConstraintEvidence(
            key=f"declared-compatible-capability-{index}",
            value=capability,
        )
        for index, capability in enumerate(
            mapping.required_capabilities,
            start=1,
        )
    )
    matched_capabilities = tuple(
        capability
        for capability in candidate_capabilities
        if capability in mapping.required_capabilities
    )
    evidence.extend(
        ConstraintEvidence(
            key=f"matched-candidate-capability-{index}",
            value=capability,
        )
        for index, capability in enumerate(matched_capabilities, start=1)
    )
    if matched_capabilities:
        status = CapabilityCompatibilityStatus.COMPATIBLE
        reason = CapabilityCompatibilityReason(
            code="explicit-capability-match",
            message=(
                "An explicit mapping matches a candidate capability."
            ),
        )
    else:
        status = CapabilityCompatibilityStatus.INCOMPATIBLE
        reason = CapabilityCompatibilityReason(
            code="no-explicit-capability-match",
            message=(
                "The authoritative mapping matches no candidate capability."
            ),
        )
    return CapabilityCompatibilityEvaluation(
        status=status,
        required_capability=required,
        candidate_capabilities=candidate_capabilities,
        reason=reason,
        evidence=tuple(evidence),
    )
