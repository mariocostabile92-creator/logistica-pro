from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


MappingStatus = Literal["MATCHED", "UNMAPPED", "AMBIGUOUS"]


class ReconciliationSummary(BaseModel):
    total: int = Field(default=0, ge=0)
    matched: int = Field(default=0, ge=0)
    unmapped: int = Field(default=0, ge=0)
    ambiguous: int = Field(default=0, ge=0)


class ReconciliationRow(BaseModel):
    transporter_external_id: str
    mapping_status: MappingStatus
    workforce_member_id: int | None = None
    workforce_display_name: str | None = None
    delivered: str | None = None
    verified_at: datetime | None = None
    verified_by: str | None = None
    updated_at: datetime | None = None


class ReconciliationState(BaseModel):
    available: bool
    week: int | None = None
    year: int | None = None
    summary: ReconciliationSummary = Field(default_factory=ReconciliationSummary)
    rows: list[ReconciliationRow] = Field(default_factory=list)


class MappingWriteRequest(BaseModel):
    workforce_member_id: int = Field(gt=0)
    expected_updated_at: datetime | None = None


class MappingRemoveRequest(BaseModel):
    expected_updated_at: datetime


class MappingWriteResult(BaseModel):
    transporter_external_id: str
    mapping_status: Literal["MATCHED", "UNMAPPED"]
    workforce_member_id: int | None = None
    workforce_display_name: str | None = None
    verified_at: datetime | None = None
    verified_by: str | None = None
    updated_at: datetime


class MappingHistoryItem(BaseModel):
    action: Literal["mapping_created", "mapping_replaced", "mapping_removed"]
    actor: str
    created_at: datetime
    previous_workforce_member_id: int | None = None
    previous_workforce_display_name: str | None = None
    new_workforce_member_id: int | None = None
    new_workforce_display_name: str | None = None


class MappingHistory(BaseModel):
    transporter_external_id: str
    items: list[MappingHistoryItem] = Field(default_factory=list)


class WorkforceCandidate(BaseModel):
    workforce_member_id: int
    display_name: str
    external_identifier: str | None = None
    station: str | None = None
    contract: str | None = None
    active: bool = True


class WorkforceCandidateList(BaseModel):
    items: list[WorkforceCandidate] = Field(default_factory=list)

