from app.domain.workforce_auto_planning.approved_assignment_conflict import (
    ApprovedAssignmentConflictStatus,
    evaluate_approved_assignment_conflict,
)
from app.domain.workforce_auto_planning.capability_compatibility import (
    CapabilityCompatibilityStatus,
    evaluate_capability_compatibility,
)
from app.domain.workforce_auto_planning.constraint_evaluation import (
    ConstraintEvaluation,
    ConstraintEvaluationCategory,
    ConstraintEvidence,
)
from app.domain.workforce_auto_planning.contract_date_eligibility import (
    ContractDateEligibilityStatus,
    evaluate_contract_date_eligibility,
)
from app.domain.workforce_auto_planning.operational_demand import (
    OperationalDemand,
)
from app.domain.workforce_auto_planning.operational_demand_trace import (
    compute_operational_demand_trace_id,
)
from app.domain.workforce_auto_planning.planning_policy import (
    WorkloadCapabilityMapping,
)
from app.domain.workforce_auto_planning.weekly_planning_input_snapshot import (
    CandidateOperationalUnitScopeStatus,
    WorkforceCandidateSnapshot,
)
from app.domain.workforce_auto_planning.weekly_hours_capacity import (
    WeeklyHoursCapacityStatus,
    evaluate_weekly_hours_capacity,
)
from app.domain.workforce_auto_planning.workforce_eligibility_decision import (
    EligibilityDecisionNotice,
    WorkforceEligibilityDecision,
)


_RULE_ORIGIN = "core-policy"


def _organization_evaluation(
    candidate: WorkforceCandidateSnapshot,
    demand: OperationalDemand,
) -> ConstraintEvaluation:
    passed = candidate.organization_id == demand.organization_id
    return ConstraintEvaluation(
        code="organization-match",
        category=ConstraintEvaluationCategory.HARD_CONSTRAINT,
        passed=passed,
        message=(
            "Candidate and demand belong to the same organization."
            if passed
            else "Candidate and demand belong to different organizations."
        ),
        evidence=(
            ConstraintEvidence(
                key="candidate-organization-id",
                value=candidate.organization_id,
            ),
            ConstraintEvidence(
                key="demand-organization-id",
                value=demand.organization_id,
            ),
        ),
        rule_origin=_RULE_ORIGIN,
    )


def _operational_unit_evaluation(
    candidate: WorkforceCandidateSnapshot,
) -> ConstraintEvaluation:
    scope = candidate.operational_unit_scope
    passed = scope.status == CandidateOperationalUnitScopeStatus.MATCHED
    evidence = [
        ConstraintEvidence(
            key="operational-unit-scope-status",
            value=scope.status.value,
        ),
        ConstraintEvidence(
            key="requested-operational-unit",
            value=scope.requested_unit.external_identifier,
        ),
    ]
    if scope.candidate_unit is not None:
        evidence.append(
            ConstraintEvidence(
                key="candidate-operational-unit",
                value=scope.candidate_unit.external_identifier,
            )
        )
    messages = {
        CandidateOperationalUnitScopeStatus.MATCHED: (
            "Candidate operational unit matches the requested unit."
        ),
        CandidateOperationalUnitScopeStatus.MISMATCHED: (
            "Candidate operational unit does not match the requested unit."
        ),
        CandidateOperationalUnitScopeStatus.UNKNOWN: (
            "Candidate operational unit is unknown."
        ),
    }
    return ConstraintEvaluation(
        code="operational-unit-match",
        category=ConstraintEvaluationCategory.HARD_CONSTRAINT,
        passed=passed,
        message=messages[scope.status],
        evidence=tuple(evidence),
        rule_origin=_RULE_ORIGIN,
    )


def _daily_callability_evaluation(
    candidate: WorkforceCandidateSnapshot,
    demand: OperationalDemand,
) -> ConstraintEvaluation:
    readiness = next(
        (
            item
            for item in candidate.availability
            if item.date == demand.date
        ),
        None,
    )
    evidence = [
        ConstraintEvidence(
            key="operational-date",
            value=demand.date.isoformat(),
        ),
        ConstraintEvidence(
            key="readiness-present",
            value=readiness is not None,
        ),
    ]
    if readiness is None:
        passed = False
        message = "No authoritative daily readiness is available."
    else:
        availability = readiness.availability
        observed_state = str(availability.observed_state or "").strip()
        state_is_known = bool(observed_state) and (
            observed_state.casefold() != "unknown"
        )
        passed = availability.available is True and state_is_known
        evidence.extend(
            (
                ConstraintEvidence(
                    key="callable",
                    value=availability.available,
                ),
                ConstraintEvidence(
                    key="observed-state",
                    value=availability.observed_state,
                ),
                ConstraintEvidence(
                    key="readiness-reason",
                    value=availability.reason,
                ),
                ConstraintEvidence(
                    key="readiness-origin",
                    value=availability.origin,
                ),
            )
        )
        limitation_prefix = (
            f"workforce-readiness:{demand.date.isoformat()}:limitation:"
        )
        evidence.extend(
            ConstraintEvidence(
                key=f"readiness-limitation-{index}",
                value=item.value,
            )
            for index, item in enumerate(
                (
                    item
                    for item in candidate.evidence
                    if item.key.startswith(limitation_prefix)
                ),
                start=1,
            )
        )
        if not state_is_known:
            message = "Daily readiness status is unknown."
        elif not availability.available:
            message = "Candidate is not callable on the operational date."
        else:
            message = "Candidate is callable on the operational date."
    return ConstraintEvaluation(
        code="daily-callability",
        category=ConstraintEvaluationCategory.HARD_CONSTRAINT,
        passed=passed,
        message=message,
        evidence=tuple(evidence),
        rule_origin=_RULE_ORIGIN,
    )


def _approved_assignment_conflict_evaluation(
    candidate: WorkforceCandidateSnapshot,
    demand: OperationalDemand,
) -> ConstraintEvaluation:
    assignments = tuple(sorted(
        candidate.already_approved_assignments,
        key=lambda assignment: (
            assignment.date,
            assignment.assignment_reference,
            assignment.time_window.external_identifier,
            assignment.shift_identifier or "",
        ),
    ))
    results = tuple(
        (
            assignment,
            evaluate_approved_assignment_conflict(
                assignment=assignment,
                demand=demand,
            ),
        )
        for assignment in assignments
    )
    statuses = {result.status for _assignment, result in results}
    if ApprovedAssignmentConflictStatus.CONFLICT in statuses:
        aggregate_status = ApprovedAssignmentConflictStatus.CONFLICT
        passed = False
        message = "An approved assignment has a confirmed time conflict."
    elif ApprovedAssignmentConflictStatus.UNKNOWN in statuses:
        aggregate_status = ApprovedAssignmentConflictStatus.UNKNOWN
        passed = False
        message = (
            "Approved assignment conflict status cannot be determined."
        )
    else:
        aggregate_status = ApprovedAssignmentConflictStatus.NO_CONFLICT
        passed = True
        message = (
            "Approved assignments do not conflict with the demand."
            if results
            else "Candidate has no approved assignments."
        )

    evidence = [
        ConstraintEvidence(
            key="approved-assignment-count",
            value=len(results),
        ),
        ConstraintEvidence(
            key="aggregate-conflict-status",
            value=aggregate_status.value,
        ),
    ]
    for index, (assignment, result) in enumerate(results, start=1):
        prefix = f"approved-assignment-{index}"
        evidence.extend(
            (
                ConstraintEvidence(
                    key=f"{prefix}:reference",
                    value=assignment.assignment_reference,
                ),
                ConstraintEvidence(
                    key=f"{prefix}:status",
                    value=result.status.value,
                ),
                ConstraintEvidence(
                    key=f"{prefix}:reason-code",
                    value=result.reason.code,
                ),
            )
        )
        evidence.extend(
            ConstraintEvidence(
                key=f"{prefix}:{item.key}",
                value=item.value,
            )
            for item in result.evidence
        )
    return ConstraintEvaluation(
        code="approved-assignment-conflict",
        category=ConstraintEvaluationCategory.HARD_CONSTRAINT,
        passed=passed,
        message=message,
        evidence=tuple(evidence),
        rule_origin=_RULE_ORIGIN,
    )


def _capability_compatibility_evaluation(
    candidate: WorkforceCandidateSnapshot,
    demand: OperationalDemand,
    capability_mappings: tuple[WorkloadCapabilityMapping, ...],
) -> ConstraintEvaluation:
    result = evaluate_capability_compatibility(
        required_capability=demand.capability_or_workload,
        candidate_capabilities=candidate.human_resource.capabilities,
        mappings=capability_mappings,
    )
    evidence = (
        ConstraintEvidence(
            key="capability-compatibility-status",
            value=result.status.value,
        ),
        ConstraintEvidence(
            key="capability-compatibility-reason-code",
            value=result.reason.code,
        ),
        *result.evidence,
    )
    return ConstraintEvaluation(
        code="capability-compatibility",
        category=ConstraintEvaluationCategory.HARD_CONSTRAINT,
        passed=result.status == CapabilityCompatibilityStatus.COMPATIBLE,
        message=result.reason.message,
        evidence=evidence,
        rule_origin=_RULE_ORIGIN,
    )


def _contract_date_validity_evaluation(
    candidate: WorkforceCandidateSnapshot,
    demand: OperationalDemand,
) -> ConstraintEvaluation:
    result = evaluate_contract_date_eligibility(
        contract_state=candidate.applicable_contract_state,
        operational_date=demand.date,
    )
    evidence = (
        ConstraintEvidence(
            key="contract-date-eligibility-status",
            value=result.status.value,
        ),
        ConstraintEvidence(
            key="contract-date-eligibility-reason-code",
            value=result.reason.code,
        ),
        *result.evidence,
    )
    return ConstraintEvaluation(
        code="contract-date-validity",
        category=ConstraintEvaluationCategory.HARD_CONSTRAINT,
        passed=result.status == ContractDateEligibilityStatus.ELIGIBLE,
        message=result.reason.message,
        evidence=evidence,
        rule_origin=_RULE_ORIGIN,
    )


def _weekly_hours_capacity_evaluation(
    candidate: WorkforceCandidateSnapshot,
    demand: OperationalDemand,
) -> ConstraintEvaluation:
    result = evaluate_weekly_hours_capacity(
        contract_state=candidate.applicable_contract_state,
        assigned_time=candidate.already_assigned_minutes_or_hours,
        demand=demand,
    )
    evidence = (
        ConstraintEvidence(
            key="weekly-hours-capacity-status",
            value=result.status.value,
        ),
        ConstraintEvidence(
            key="weekly-hours-capacity-reason-code",
            value=result.reason.code,
        ),
        *result.evidence,
    )
    return ConstraintEvaluation(
        code="weekly-hours-capacity",
        category=ConstraintEvaluationCategory.HARD_CONSTRAINT,
        passed=result.status == WeeklyHoursCapacityStatus.SUFFICIENT,
        message=result.reason.message,
        evidence=evidence,
        rule_origin=_RULE_ORIGIN,
    )


def evaluate_workforce_candidate_eligibility(
    *,
    candidate: WorkforceCandidateSnapshot,
    demand: OperationalDemand,
    capability_mappings: tuple[WorkloadCapabilityMapping, ...],
) -> WorkforceEligibilityDecision:
    evaluations = (
        _organization_evaluation(candidate, demand),
        _operational_unit_evaluation(candidate),
        _daily_callability_evaluation(candidate, demand),
        _approved_assignment_conflict_evaluation(candidate, demand),
        _capability_compatibility_evaluation(
            candidate,
            demand,
            capability_mappings,
        ),
        _contract_date_validity_evaluation(candidate, demand),
        _weekly_hours_capacity_evaluation(candidate, demand),
    )
    exclusion_reasons = tuple(
        EligibilityDecisionNotice(
            code=evaluation.code,
            message=evaluation.message,
        )
        for evaluation in evaluations
        if not evaluation.passed
    )
    return WorkforceEligibilityDecision(
        demand_trace_id=compute_operational_demand_trace_id(demand),
        organization_id=demand.organization_id,
        workforce_member_id=candidate.workforce_member_id,
        operational_date=demand.date,
        operational_unit=demand.operational_unit,
        time_window=demand.time_window,
        capability_or_workload=demand.capability_or_workload,
        eligible=all(evaluation.passed for evaluation in evaluations),
        evaluations=evaluations,
        exclusion_reasons=exclusion_reasons,
        warnings=(),
    )
