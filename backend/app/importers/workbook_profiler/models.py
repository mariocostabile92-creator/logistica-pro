from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class WorkbookType(str, Enum):
    DAILY_OPERATIONAL_PLANNING = "DAILY_OPERATIONAL_PLANNING"
    WORKFORCE_SCHEDULE = "WORKFORCE_SCHEDULE"
    FLEET_REGISTRY = "FLEET_REGISTRY"
    UNKNOWN_WORKBOOK = "UNKNOWN_WORKBOOK"


@dataclass(frozen=True)
class ScannedSheet:
    name: str
    rows: list[list[Any]]
    formula_cells: frozenset[tuple[int, int]] = frozenset()
    merged_ranges: tuple[tuple[int, int, int, int], ...] = ()

    @property
    def total_rows(self) -> int:
        return len(self.rows)

    @property
    def total_columns(self) -> int:
        return max((len(row) for row in self.rows), default=0)


@dataclass(frozen=True)
class ScannedWorkbook:
    sheets: tuple[ScannedSheet, ...]
    metrics: dict[str, float] = field(default_factory=dict)


class HeaderCandidate(BaseModel):
    row_index: int = Field(ge=1)
    confidence: float = Field(ge=0, le=1)
    reason: str
    matched_fields: list[str] = Field(default_factory=list)
    nonempty_cells: int = Field(default=0, ge=0)
    manually_selected: bool = False


class SheetProfile(BaseModel):
    name: str
    total_rows: int = Field(ge=0)
    total_columns: int = Field(ge=0)
    score: float = Field(ge=0, le=1)
    reason: str
    header_row: int | None = None
    header_confidence: float = Field(default=0, ge=0, le=1)
    header_candidates: list[HeaderCandidate] = Field(default_factory=list)
    data_rows: int = Field(default=0, ge=0)
    formula_ratio: float = Field(default=0, ge=0, le=1)
    ignored: bool = False


class WorkbookClassification(BaseModel):
    workbook_type: WorkbookType
    confidence: float = Field(ge=0, le=1)
    reason: str


class ProfileIssue(BaseModel):
    code: str
    message: str


class MappingFieldOption(BaseModel):
    value: str
    label: str


@dataclass
class ProfiledWorkbook:
    classification: WorkbookClassification
    selected_sheet: ScannedSheet
    selected_sheet_profile: SheetProfile
    sheet_profiles: list[SheetProfile]
    selected_header: HeaderCandidate | None
    columns: list[str]
    table_rows: list[dict[str, Any]]
    row_numbers: list[int]
    mapping: list[Any]
    recognized_columns: list[Any]
    ignored_columns: list[str]
    unknown_columns: list[str]
    mapping_options: list[MappingFieldOption]
    mapping_confidence: float
    import_allowed: bool
    blocking_reasons: list[ProfileIssue] = field(default_factory=list)
    warnings: list[ProfileIssue] = field(default_factory=list)
    sample_rows: list[dict[str, Any]] = field(default_factory=list)
