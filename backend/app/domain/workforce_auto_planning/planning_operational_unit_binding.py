from typing import Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.domain.core_language import OperationalUnit


class PlanningOperationalUnitBinding(BaseModel):
    model_config = ConfigDict(frozen=True, str_strip_whitespace=True)

    organization_id: str = Field(min_length=1)
    demand_source_context: str = Field(min_length=1)
    operational_unit: OperationalUnit
    binding_version: int = Field(gt=0, strict=True)
    active: bool = Field(strict=True)

    @model_validator(mode="after")
    def validate_operational_unit(self) -> "PlanningOperationalUnitBinding":
        if not self.operational_unit.external_identifier.strip():
            raise ValueError("operational_unit external_identifier cannot be empty")
        return self


@runtime_checkable
class PlanningOperationalUnitBindingProvider(Protocol):
    def resolve_binding(
        self,
        *,
        organization_id: str,
        demand_source_context: str,
    ) -> PlanningOperationalUnitBinding:
        """Return the single active binding or fail without applying a fallback."""
        ...
