from datetime import date as CalendarDate

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

from app.domain.core_language import OperationalUnit, TimeWindow


class CoverageGapReason(BaseModel):
    model_config = ConfigDict(frozen=True, str_strip_whitespace=True)

    code: str = Field(min_length=1)
    message: str = Field(min_length=1)


class CoverageGap(BaseModel):
    model_config = ConfigDict(frozen=True, str_strip_whitespace=True)

    demand_trace_id: str = Field(min_length=1)
    organization_id: str = Field(min_length=1)
    date: CalendarDate
    operational_unit: OperationalUnit
    time_window: TimeWindow
    capability_or_workload: str = Field(min_length=1)
    required_quantity: int = Field(ge=0, strict=True)
    proposed_quantity: int = Field(ge=0, strict=True)
    gap_quantity: int = Field(strict=True)
    reason: CoverageGapReason
    excluded_candidate_categories: tuple[str, ...] = Field(
        default_factory=tuple
    )

    @field_validator("excluded_candidate_categories")
    @classmethod
    def validate_excluded_candidate_categories(
        cls,
        categories: tuple[str, ...],
    ) -> tuple[str, ...]:
        if any(not category.strip() for category in categories):
            raise ValueError("excluded candidate category cannot be empty")
        return categories

    @model_validator(mode="after")
    def validate_gap(self) -> "CoverageGap":
        if not self.operational_unit.external_identifier.strip():
            raise ValueError("operational_unit cannot be empty")
        expected_gap = self.required_quantity - self.proposed_quantity
        if self.gap_quantity != expected_gap:
            raise ValueError(
                "gap_quantity must equal required_quantity - proposed_quantity"
            )
        return self
