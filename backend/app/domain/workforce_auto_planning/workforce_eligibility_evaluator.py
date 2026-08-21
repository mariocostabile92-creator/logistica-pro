from app.domain.workforce_auto_planning.constraint_evaluation import (
    ConstraintEvaluation,
    ConstraintEvaluationCategory,
    ConstraintEvidence,
)
from app.domain.workforce_auto_planning.operational_demand import (
    OperationalDemand,
)
from app.domain.workforce_auto_planning.weekly_planning_input_snapshot import (
    CandidateOperationalUnitScopeStatus,
    WorkforceCandidateSnapshot,
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


def evaluate_workforce_candidate_eligibility(
    *,
    candidate: WorkforceCandidateSnapshot,
    demand: OperationalDemand,
) -> WorkforceEligibilityDecision:
    evaluations = (
        _organization_evaluation(candidate, demand),
        _operational_unit_evaluation(candidate),
        _daily_callability_evaluation(candidate, demand),
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
