from app.domain.workforce_auto_planning.approved_assignment_conflict import (
    ApprovedAssignmentConflictEvaluation,
    ApprovedAssignmentConflictReason,
    ApprovedAssignmentConflictStatus,
    evaluate_approved_assignment_conflict,
)
from app.domain.workforce_auto_planning.capability_compatibility import (
    AmbiguousCapabilityMappingError,
    CapabilityCompatibilityEvaluation,
    CapabilityCompatibilityReason,
    CapabilityCompatibilityStatus,
    evaluate_capability_compatibility,
)
from app.domain.workforce_auto_planning.candidate_ranking import (
    DeterministicCandidateRankingKey,
    PreferenceRankingKeyEntry,
    RankedWorkforceCandidate,
    WorkforceCandidateRankingInput,
    rank_eligible_workforce_candidates,
)
from app.domain.workforce_auto_planning.baseline_preference_composer import (
    build_baseline_workforce_preference_sets,
)
from app.domain.workforce_auto_planning.constraint_evaluation import (
    ConstraintEvaluation,
    ConstraintEvaluationCategory,
    ConstraintEvidence,
    ConstraintEvidenceValue,
    ConstraintRemediation,
)
from app.domain.workforce_auto_planning.dispatcher_assignment_lock import (
    DispatcherAssignmentLockAssignmentNotFoundError,
    DispatcherAssignmentLockCommand,
    DispatcherAssignmentLockError,
    DispatcherAssignmentLockScopeMismatchError,
    apply_dispatcher_assignment_lock,
)
from app.domain.workforce_auto_planning.dispatcher_manual_override import (
    DispatcherManualOverride,
    DispatcherOverrideOperationType,
)
from app.domain.workforce_auto_planning.dispatcher_manual_override_revalidation import (
    DispatcherManualOverrideCandidateNotFoundError,
    DispatcherManualOverrideDemandNotFoundError,
    DispatcherManualOverrideRevalidationError,
    revalidate_dispatcher_manual_override,
)
from app.domain.workforce_auto_planning.dispatcher_weekly_edit import (
    DispatcherWeeklyEditAssignmentNotFoundError,
    DispatcherWeeklyEditCommand,
    DispatcherWeeklyEditCommandMismatchError,
    DispatcherWeeklyEditError,
    DispatcherWeeklyEditScopeMismatchError,
    DispatcherWeeklyEditUnknownDemandTraceError,
    apply_dispatcher_weekly_edit,
)
from app.domain.workforce_auto_planning.contract_date_eligibility import (
    ContractDateEligibilityEvaluation,
    ContractDateEligibilityStatus,
    evaluate_contract_date_eligibility,
)
from app.domain.workforce_auto_planning.existing_assignment_stability_preference import (
    evaluate_existing_assignment_stability_preference,
)
from app.domain.workforce_auto_planning.continuity_preference import (
    evaluate_continuity_preference,
)
from app.domain.workforce_auto_planning.lower_weekly_load_preference import (
    evaluate_lower_weekly_load_preference,
)
from app.domain.workforce_auto_planning.locked_assignment_preservation import (
    LockedAssignmentConflict,
    LockedAssignmentConflictReason,
    LockedAssignmentConflictStatus,
    LockedAssignmentDuplicateIdentityError,
    LockedAssignmentPreservationError,
    LockedAssignmentPreservationSet,
    LockedAssignmentScopeMismatchError,
    LockedAssignmentUnknownDemandTraceError,
    LockedDemandCoverage,
    build_locked_assignment_preservation_set,
)
from app.domain.workforce_auto_planning.locked_weekly_proposal_generator import (
    generate_weekly_proposal_preserving_locked,
)
from app.domain.workforce_auto_planning.coverage_gap import (
    CoverageGap,
    CoverageGapReason,
)
from app.domain.workforce_auto_planning.operational_demand import (
    AppliedPolicyAttribute,
    AppliedPolicyMetadata,
    OperationalDemand,
)
from app.domain.workforce_auto_planning.operational_demand_trace import (
    compute_operational_demand_trace_id,
)
from app.domain.workforce_auto_planning.planning_policy import (
    OperationalBufferPolicy,
    PlanningPriorityOrPreference,
    PlanningRuleDescriptor,
    PlanningRuleParameter,
    ShiftCatalogueEntry,
    WorkforcePlanningPolicyProvider,
    WorkloadCapabilityMapping,
)
from app.domain.workforce_auto_planning.planning_operational_unit_binding import (
    PlanningOperationalUnitBinding,
    PlanningOperationalUnitBindingProvider,
)
from app.domain.workforce_auto_planning.planning_preference import (
    PlanningPreferenceEvaluation,
    PlanningPreferenceOutcome,
    WorkforcePlanningPreferenceSet,
)
from app.domain.workforce_auto_planning.proposed_shift_assignment import (
    ProposedAssignmentReason,
    ProposedShiftAssignment,
    ProposedShiftAssignmentOrigin,
    ProposedShiftAssignmentStatus,
)
from app.domain.workforce_auto_planning.snapshot_provider_ports import (
    OperationalDemandProvider,
    WorkforceCandidateSnapshotProvider,
)
from app.domain.workforce_auto_planning.weekly_workforce_proposal import (
    WeeklyWorkforceProposal,
    WeeklyWorkforceProposalStatus,
)
from app.domain.workforce_auto_planning.weekly_planning_input_snapshot import (
    ApprovedAssignmentSnapshot,
    AssignedTimeSnapshot,
    AssignedTimeStatus,
    AssignedTimeUnit,
    CandidateOperationalUnitScope,
    CandidateOperationalUnitScopeStatus,
    ContractStateSourceKind,
    CurrentMemberContractStateSnapshot,
    WeeklyPlanningInputSnapshot,
    WorkforceCandidateAvailabilitySnapshot,
    WorkforceCandidateSnapshot,
)
from app.domain.workforce_auto_planning.weekly_proposal_generator import (
    AssignmentIdFactory,
    WeeklyProposalGenerationResult,
    generate_weekly_proposal_baseline,
)
from app.domain.workforce_auto_planning.weekly_proposal_composer import (
    ComposedWeeklyWorkforceProposal,
    WeeklyProposalCompositionError,
    compose_weekly_workforce_proposal,
)
from app.domain.workforce_auto_planning.weekly_proposal_repository import (
    WeeklyWorkforceProposalOrganizationMismatchError,
    WeeklyWorkforceProposalRepository,
    WeeklyWorkforceProposalRepositoryError,
    WeeklyWorkforceProposalRevisionAlreadyExistsError,
    WeeklyWorkforceProposalRevisionNotFoundError,
    WeeklyWorkforceProposalSnapshotMismatchError,
)
from app.domain.workforce_auto_planning.weekly_proposal_event import (
    WeeklyWorkforceProposalEvent,
)
from app.domain.workforce_auto_planning.weekly_proposal_event_repository import (
    WeeklyWorkforceProposalEventAlreadyExistsError,
    WeeklyWorkforceProposalEventOrganizationMismatchError,
    WeeklyWorkforceProposalEventRepository,
    WeeklyWorkforceProposalEventRepositoryError,
)
from app.domain.workforce_auto_planning.weekly_proposal_revision import (
    WeeklyProposalRevisionCompositionError,
    compose_next_weekly_proposal_revision,
)
from app.domain.workforce_auto_planning.weekly_proposal_status_transition import (
    WeeklyProposalStatusTransitionCommand,
    WeeklyProposalStatusTransitionError,
    WeeklyProposalStatusTransitionNotAllowedError,
    WeeklyProposalStatusTransitionScopeMismatchError,
    apply_weekly_proposal_status_transition,
)
from app.domain.workforce_auto_planning.weekly_hours_capacity import (
    WeeklyHoursCapacityEvaluation,
    WeeklyHoursCapacityStatus,
    evaluate_weekly_hours_capacity,
)
from app.domain.workforce_auto_planning.weekly_snapshot_fingerprint import (
    compute_weekly_planning_input_fingerprint,
)
from app.domain.workforce_auto_planning.weekly_snapshot_composer import (
    WeeklyPlanningInputSnapshotComposer,
)
from app.domain.workforce_auto_planning.workforce_eligibility_decision import (
    EligibilityDecisionNotice,
    WorkforceEligibilityDecision,
)
from app.domain.workforce_auto_planning.workforce_eligibility_evaluator import (
    evaluate_workforce_candidate_eligibility,
)


__all__ = [
    "AmbiguousCapabilityMappingError",
    "ApprovedAssignmentConflictEvaluation",
    "ApprovedAssignmentConflictReason",
    "ApprovedAssignmentConflictStatus",
    "AppliedPolicyAttribute",
    "AppliedPolicyMetadata",
    "ApprovedAssignmentSnapshot",
    "AssignedTimeSnapshot",
    "AssignedTimeStatus",
    "AssignedTimeUnit",
    "AssignmentIdFactory",
    "apply_dispatcher_assignment_lock",
    "apply_dispatcher_weekly_edit",
    "build_baseline_workforce_preference_sets",
    "build_locked_assignment_preservation_set",
    "CandidateOperationalUnitScope",
    "CandidateOperationalUnitScopeStatus",
    "ComposedWeeklyWorkforceProposal",
    "DeterministicCandidateRankingKey",
    "CapabilityCompatibilityEvaluation",
    "CapabilityCompatibilityReason",
    "CapabilityCompatibilityStatus",
    "ContractStateSourceKind",
    "ContractDateEligibilityEvaluation",
    "ContractDateEligibilityStatus",
    "ConstraintEvaluation",
    "ConstraintEvaluationCategory",
    "ConstraintEvidence",
    "ConstraintEvidenceValue",
    "ConstraintRemediation",
    "CoverageGap",
    "CoverageGapReason",
    "CurrentMemberContractStateSnapshot",
    "DispatcherAssignmentLockAssignmentNotFoundError",
    "DispatcherAssignmentLockCommand",
    "DispatcherAssignmentLockError",
    "DispatcherAssignmentLockScopeMismatchError",
    "DispatcherManualOverride",
    "DispatcherManualOverrideCandidateNotFoundError",
    "DispatcherManualOverrideDemandNotFoundError",
    "DispatcherManualOverrideRevalidationError",
    "DispatcherOverrideOperationType",
    "DispatcherWeeklyEditAssignmentNotFoundError",
    "DispatcherWeeklyEditCommand",
    "DispatcherWeeklyEditCommandMismatchError",
    "DispatcherWeeklyEditError",
    "DispatcherWeeklyEditScopeMismatchError",
    "DispatcherWeeklyEditUnknownDemandTraceError",
    "EligibilityDecisionNotice",
    "LockedAssignmentConflict",
    "LockedAssignmentConflictReason",
    "LockedAssignmentConflictStatus",
    "LockedAssignmentDuplicateIdentityError",
    "LockedAssignmentPreservationError",
    "LockedAssignmentPreservationSet",
    "LockedAssignmentScopeMismatchError",
    "LockedAssignmentUnknownDemandTraceError",
    "LockedDemandCoverage",
    "OperationalBufferPolicy",
    "OperationalDemand",
    "OperationalDemandProvider",
    "PlanningPriorityOrPreference",
    "PlanningPreferenceEvaluation",
    "PlanningPreferenceOutcome",
    "PreferenceRankingKeyEntry",
    "PlanningOperationalUnitBinding",
    "PlanningOperationalUnitBindingProvider",
    "PlanningRuleDescriptor",
    "PlanningRuleParameter",
    "ProposedAssignmentReason",
    "ProposedShiftAssignment",
    "ProposedShiftAssignmentOrigin",
    "ProposedShiftAssignmentStatus",
    "RankedWorkforceCandidate",
    "ShiftCatalogueEntry",
    "WorkforcePlanningPolicyProvider",
    "WorkforcePlanningPreferenceSet",
    "WorkloadCapabilityMapping",
    "compute_weekly_planning_input_fingerprint",
    "compute_operational_demand_trace_id",
    "compose_weekly_workforce_proposal",
    "compose_next_weekly_proposal_revision",
    "apply_weekly_proposal_status_transition",
    "evaluate_approved_assignment_conflict",
    "evaluate_capability_compatibility",
    "evaluate_contract_date_eligibility",
    "evaluate_existing_assignment_stability_preference",
    "evaluate_continuity_preference",
    "evaluate_lower_weekly_load_preference",
    "evaluate_weekly_hours_capacity",
    "rank_eligible_workforce_candidates",
    "revalidate_dispatcher_manual_override",
    "evaluate_workforce_candidate_eligibility",
    "WeeklyWorkforceProposal",
    "WeeklyWorkforceProposalStatus",
    "WeeklyPlanningInputSnapshot",
    "WeeklyPlanningInputSnapshotComposer",
    "WeeklyProposalGenerationResult",
    "WeeklyProposalCompositionError",
    "WeeklyProposalRevisionCompositionError",
    "WeeklyProposalStatusTransitionCommand",
    "WeeklyProposalStatusTransitionError",
    "WeeklyProposalStatusTransitionNotAllowedError",
    "WeeklyProposalStatusTransitionScopeMismatchError",
    "WeeklyWorkforceProposalOrganizationMismatchError",
    "WeeklyWorkforceProposalRepository",
    "WeeklyWorkforceProposalRepositoryError",
    "WeeklyWorkforceProposalRevisionAlreadyExistsError",
    "WeeklyWorkforceProposalRevisionNotFoundError",
    "WeeklyWorkforceProposalSnapshotMismatchError",
    "WeeklyWorkforceProposalEvent",
    "WeeklyWorkforceProposalEventAlreadyExistsError",
    "WeeklyWorkforceProposalEventOrganizationMismatchError",
    "WeeklyWorkforceProposalEventRepository",
    "WeeklyWorkforceProposalEventRepositoryError",
    "WeeklyHoursCapacityEvaluation",
    "WeeklyHoursCapacityStatus",
    "WorkforceCandidateAvailabilitySnapshot",
    "WorkforceCandidateSnapshot",
    "WorkforceCandidateSnapshotProvider",
    "WorkforceCandidateRankingInput",
    "WorkforceEligibilityDecision",
    "generate_weekly_proposal_baseline",
    "generate_weekly_proposal_preserving_locked",
]
