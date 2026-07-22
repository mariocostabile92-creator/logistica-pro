from datetime import date, datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.domain.core_language import OperationalUnit


class _DraftModel(BaseModel):
    model_config = ConfigDict(frozen=True, str_strip_whitespace=True)


def _timezone_aware(value: datetime) -> datetime:
    if value.utcoffset() is None:
        raise ValueError("A timezone-aware datetime is required.")
    return value


class PlanningDraftState(str, Enum):
    EMPTY = "EMPTY"
    CREATED = "CREATED"
    DIRTY = "DIRTY"
    SAVED = "SAVED"
    READ_ONLY = "READ_ONLY"
    ERROR = "ERROR"


class PlanningDraftChangeType(str, Enum):
    CREATED = "CREATED"
    METADATA_UPDATED = "METADATA_UPDATED"
    SAVED = "SAVED"
    RESTORED = "RESTORED"
    DELETED = "DELETED"


class PlanningDraftScope(_DraftModel):
    organization_id: str = Field(min_length=1, max_length=120)
    operational_unit: OperationalUnit
    planning_date: date


class PlanningDraftMetadata(_DraftModel):
    name: str = Field(min_length=1, max_length=120)
    note: str | None = Field(default=None, max_length=1000)


class PlanningDraftVersion(_DraftModel):
    number: int = Field(ge=1)
    created_at: datetime
    created_by: str = Field(min_length=1, max_length=120)
    restored_from_version: int | None = Field(default=None, ge=1)

    _validate_created_at = field_validator("created_at")(_timezone_aware)


class PlanningDraft(_DraftModel):
    draft_id: str = Field(min_length=1, max_length=120)
    scope: PlanningDraftScope
    metadata: PlanningDraftMetadata
    state: PlanningDraftState
    version: PlanningDraftVersion
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None = None

    _validate_created_at = field_validator("created_at")(_timezone_aware)
    _validate_updated_at = field_validator("updated_at")(_timezone_aware)

    @field_validator("deleted_at")
    @classmethod
    def validate_deleted_at(cls, value):
        return _timezone_aware(value) if value is not None else value

    @model_validator(mode="after")
    def validate_lifecycle(self):
        if self.state in {
            PlanningDraftState.EMPTY,
            PlanningDraftState.ERROR,
        }:
            raise ValueError("A persisted Draft requires a concrete state.")
        if self.state is PlanningDraftState.READ_ONLY and self.deleted_at is None:
            raise ValueError("A deleted Draft requires deleted_at.")
        if self.state is not PlanningDraftState.READ_ONLY and self.deleted_at:
            raise ValueError("Only a read-only Draft can be deleted.")
        if self.updated_at < self.created_at:
            raise ValueError("updated_at cannot precede created_at.")
        return self


class PlanningDraftSnapshot(_DraftModel):
    snapshot_id: str = Field(min_length=1, max_length=120)
    draft_id: str = Field(min_length=1, max_length=120)
    state: PlanningDraftState
    version: PlanningDraftVersion
    metadata: PlanningDraftMetadata

    @field_validator("state")
    @classmethod
    def validate_state(cls, value):
        if value in {PlanningDraftState.EMPTY, PlanningDraftState.ERROR}:
            raise ValueError("A snapshot requires a concrete Draft state.")
        return value


class PlanningDraftChangeMetadata(_DraftModel):
    key: str = Field(min_length=1, max_length=120)
    value: str = Field(min_length=1, max_length=1000)


class PlanningDraftChange(_DraftModel):
    change_id: str = Field(min_length=1, max_length=120)
    draft_id: str = Field(min_length=1, max_length=120)
    change_type: PlanningDraftChangeType
    from_version: int | None = Field(default=None, ge=1)
    to_version: int = Field(ge=1)
    actor: str = Field(min_length=1, max_length=120)
    occurred_at: datetime
    summary: str = Field(min_length=1, max_length=500)
    metadata: tuple[PlanningDraftChangeMetadata, ...] = Field(
        default_factory=tuple,
        max_length=20,
    )

    _validate_occurred_at = field_validator("occurred_at")(_timezone_aware)


class PlanningDraftHistory(_DraftModel):
    draft_id: str = Field(min_length=1, max_length=120)
    total_changes: int = Field(ge=0)
    total_versions: int = Field(ge=0)
    changes: tuple[PlanningDraftChange, ...] = Field(
        default_factory=tuple,
        max_length=100,
    )
    snapshots: tuple[PlanningDraftSnapshot, ...] = Field(
        default_factory=tuple,
        max_length=100,
    )

    @model_validator(mode="after")
    def validate_history(self):
        if self.total_changes < len(self.changes):
            raise ValueError("total_changes cannot be smaller than the page.")
        if self.total_versions < len(self.snapshots):
            raise ValueError("total_versions cannot be smaller than the page.")
        if any(item.draft_id != self.draft_id for item in self.changes):
            raise ValueError("Every change must belong to the Draft.")
        if any(item.draft_id != self.draft_id for item in self.snapshots):
            raise ValueError("Every snapshot must belong to the Draft.")
        change_times = tuple(item.occurred_at for item in self.changes)
        if change_times != tuple(sorted(change_times, reverse=True)):
            raise ValueError("Changes must be newest first.")
        version_numbers = tuple(item.version.number for item in self.snapshots)
        if version_numbers != tuple(sorted(version_numbers, reverse=True)):
            raise ValueError("Snapshots must be newest first.")
        return self


class PlanningDraftWorkspace(_DraftModel):
    state: PlanningDraftState
    draft: PlanningDraft | None = None
    history: PlanningDraftHistory | None = None

    @model_validator(mode="after")
    def validate_workspace(self):
        if self.state is PlanningDraftState.EMPTY:
            if self.draft is not None or self.history is not None:
                raise ValueError("An empty workspace cannot expose a Draft.")
            return self
        if self.state is PlanningDraftState.ERROR:
            return self
        if self.draft is None or self.history is None:
            raise ValueError("A Draft workspace requires Draft and history.")
        if self.state is not self.draft.state:
            raise ValueError("Workspace and Draft states must match.")
        return self
