from enum import Enum

from pydantic import BaseModel, Field, JsonValue


BRIEFING_CONTRACT_VERSION = "1.0"


class BriefingStatus(str, Enum):
    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"


class AttentionLevel(str, Enum):
    STABLE = "stable"
    ATTENTION = "attention"
    CRITICAL = "critical"
    UNAVAILABLE = "unavailable"


class BriefingSeverity(str, Enum):
    BLOCKER = "blocker"
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFORMATION = "information"


class BriefingCategory(str, Enum):
    READINESS = "readiness"
    CAPACITY = "capacity"
    HUMAN_RESOURCES = "human_resources"
    ASSETS = "assets"
    PLANNING_DECISIONS = "planning_decisions"
    CRITICAL_ATTENTION = "critical_attention"


class FactProvenance(str, Enum):
    OBSERVED = "observed"
    CONFIGURED = "configured"
    DERIVED = "derived"
    SUGGESTION = "suggestion"
    LIMITATION = "limitation"


class SourceType(str, Enum):
    PLANNING = "planning"
    ASSIGNMENT = "assignment"
    CONFLICT = "conflict"
    PLANNING_ALTERNATIVE = "planning_alternative"
    READINESS = "readiness"
    CAPACITY = "capacity"
    FLEET_ASSET = "fleet_asset"
    FLEET_DOCUMENT = "fleet_document"
    PLANNING_EVENT = "planning_event"
    CONFIGURATION = "configuration"


class WorkspaceTarget(str, Enum):
    OPERATIONS = "operations"
    FLEET = "fleet"
    SETTINGS = "settings"


class SourceReference(BaseModel):
    source_type: SourceType
    source_id: str = Field(min_length=1, max_length=160)
    source_version: str | None = Field(default=None, max_length=80)
    field_path: str = Field(min_length=1, max_length=240)
    label: str = Field(min_length=1, max_length=240)


class BriefingFact(BaseModel):
    fact_id: str = Field(min_length=1, max_length=160)
    fact_type: str = Field(min_length=1, max_length=80)
    label: str = Field(min_length=1, max_length=240)
    value: JsonValue
    source_type: SourceType
    source_id: str = Field(min_length=1, max_length=160)
    source_version: str | None = Field(default=None, max_length=80)
    observed_at: str | None = Field(default=None, max_length=80)
    provenance: FactProvenance

    def source_reference(self, field_path: str) -> SourceReference:
        return SourceReference(
            source_type=self.source_type,
            source_id=self.source_id,
            source_version=self.source_version,
            field_path=field_path,
            label=self.label,
        )


class ActionLink(BaseModel):
    label: str = Field(min_length=1, max_length=120)
    workspace: WorkspaceTarget
    target_id: str = Field(min_length=1, max_length=120)
    entity_type: str | None = Field(default=None, max_length=80)
    entity_id: str | None = Field(default=None, max_length=160)


class BriefingRecommendation(BaseModel):
    recommendation_code: str = Field(min_length=1, max_length=120)
    text: str = Field(min_length=1, max_length=1000)
    reason: str = Field(min_length=1, max_length=1000)
    data_used: list[SourceReference] = Field(
        default_factory=list,
        max_length=100,
    )
    alternatives: list[str] = Field(default_factory=list, max_length=20)
    expected_impact: str = Field(min_length=1, max_length=500)
    requires_human_confirmation: bool = True
    action_link: ActionLink | None = None


class BriefingSection(BaseModel):
    section_id: str = Field(min_length=1, max_length=180)
    issue_code: str = Field(min_length=1, max_length=120)
    title: str = Field(min_length=1, max_length=240)
    category: BriefingCategory
    severity: BriefingSeverity
    priority: int = Field(ge=1)
    priority_score: int = Field(ge=0)
    urgency: int = Field(ge=1, le=4)
    operational_impact: int = Field(ge=1, le=4)
    ranking_explanation: str = Field(min_length=1, max_length=500)
    summary: str = Field(min_length=1, max_length=1200)
    facts: list[BriefingFact] = Field(default_factory=list, max_length=100)
    recommendation: BriefingRecommendation | None = None
    rationale: str = Field(min_length=1, max_length=1200)
    alternatives: list[str] = Field(default_factory=list, max_length=50)
    source_references: list[SourceReference] = Field(
        default_factory=list,
        max_length=200,
    )
    action_links: list[ActionLink] = Field(default_factory=list, max_length=20)
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    requires_human_decision: bool = True


class ReadinessSnapshot(BaseModel):
    available: bool
    level: str | None = Field(default=None, max_length=40)
    risk_level: str | None = Field(default=None, max_length=40)
    can_start_all_tasks: bool | None = None
    blocking_issues: int = Field(default=0, ge=0)
    warnings: int = Field(default=0, ge=0)
    reasons: list[str] = Field(default_factory=list, max_length=100)
    source_reference: SourceReference | None = None


class CapacitySnapshot(BaseModel):
    available: bool
    demand: int | None = Field(default=None, ge=0)
    available_capacity: int | None = Field(default=None, ge=0)
    margin: int | None = None
    reserve_threshold: int | None = Field(default=None, ge=0)
    operational_units_under_pressure: list[str] = Field(
        default_factory=list,
        max_length=200,
    )
    source_references: list[SourceReference] = Field(
        default_factory=list,
        max_length=200,
    )


class BriefingMetrics(BaseModel):
    critical_items: int = Field(default=0, ge=0)
    attention_items: int = Field(default=0, ge=0)
    information_items: int = Field(default=0, ge=0)
    recommended_actions: int = Field(default=0, ge=0)


class DailyOperationsBriefing(BaseModel):
    briefing_id: str | None = Field(default=None, max_length=160)
    briefing_revision: int | None = Field(default=None, ge=1)
    fingerprint: str | None = Field(default=None, max_length=64)
    contract_version: str = BRIEFING_CONTRACT_VERSION
    generated_at: str | None = None
    operation_date: str | None = None
    planning_id: int | None = None
    planning_version: int | None = None
    configuration_version: int | None = None
    organization_id: str | None = Field(default=None, max_length=120)
    operational_unit_ids: list[str] = Field(
        default_factory=list,
        max_length=200,
    )
    status: BriefingStatus
    executive_summary: str = Field(min_length=1, max_length=1600)
    attention_level: AttentionLevel
    attention_reason: str = Field(min_length=1, max_length=1200)
    readiness_snapshot: ReadinessSnapshot
    capacity_snapshot: CapacitySnapshot
    metrics: BriefingMetrics = Field(default_factory=BriefingMetrics)
    sections: list[BriefingSection] = Field(
        default_factory=list,
        max_length=300,
    )
    source_references: list[SourceReference] = Field(
        default_factory=list,
        max_length=1000,
    )
    limitations: list[str] = Field(default_factory=list, max_length=100)
    is_demo: bool = False
