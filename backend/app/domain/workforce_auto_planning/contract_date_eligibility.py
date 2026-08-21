from datetime import date as CalendarDate
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

from app.domain.workforce_auto_planning.constraint_evaluation import (
    ConstraintEvidence,
)
from app.domain.workforce_auto_planning.weekly_planning_input_snapshot import (
    CurrentMemberContractStateSnapshot,
)
from app.domain.workforce_auto_planning.workforce_eligibility_decision import (
    EligibilityDecisionNotice,
)


class ContractDateEligibilityStatus(str, Enum):
    ELIGIBLE = "ELIGIBLE"
    INELIGIBLE = "INELIGIBLE"


class ContractDateEligibilityEvaluation(BaseModel):
    model_config = ConfigDict(frozen=True)

    status: ContractDateEligibilityStatus
    operational_date: CalendarDate
    contract_start: CalendarDate | None = None
    contract_end: CalendarDate | None = None
    reason: EligibilityDecisionNotice
    evidence: tuple[ConstraintEvidence, ...] = Field(default_factory=tuple)


def _evidence(
    *,
    operational_date: CalendarDate,
    contract_start: CalendarDate | None,
    contract_end: CalendarDate | None,
) -> tuple[ConstraintEvidence, ...]:
    return (
        ConstraintEvidence(
            key="operational-date",
            value=operational_date.isoformat(),
        ),
        ConstraintEvidence(
            key="contract-start",
            value=(
                contract_start.isoformat()
                if contract_start is not None
                else None
            ),
        ),
        ConstraintEvidence(
            key="contract-end",
            value=(
                contract_end.isoformat()
                if contract_end is not None
                else None
            ),
        ),
    )


def _result(
    *,
    status: ContractDateEligibilityStatus,
    operational_date: CalendarDate,
    contract_start: CalendarDate | None,
    contract_end: CalendarDate | None,
    reason_code: str,
    reason_message: str,
) -> ContractDateEligibilityEvaluation:
    return ContractDateEligibilityEvaluation(
        status=status,
        operational_date=operational_date,
        contract_start=contract_start,
        contract_end=contract_end,
        reason=EligibilityDecisionNotice(
            code=reason_code,
            message=reason_message,
        ),
        evidence=_evidence(
            operational_date=operational_date,
            contract_start=contract_start,
            contract_end=contract_end,
        ),
    )


def evaluate_contract_date_eligibility(
    *,
    contract_state: CurrentMemberContractStateSnapshot,
    operational_date: CalendarDate,
) -> ContractDateEligibilityEvaluation:
    contract_start = contract_state.contract_start
    contract_end = contract_state.contract_end

    if contract_start is None and contract_end is None:
        return _result(
            status=ContractDateEligibilityStatus.ELIGIBLE,
            operational_date=operational_date,
            contract_start=None,
            contract_end=None,
            reason_code="no-contract-date-limits",
            reason_message="No authoritative contract date limits are available.",
        )

    if contract_start is not None and operational_date < contract_start:
        return _result(
            status=ContractDateEligibilityStatus.INELIGIBLE,
            operational_date=operational_date,
            contract_start=contract_start,
            contract_end=contract_end,
            reason_code="before-contract-start",
            reason_message="The operational date precedes the contract start.",
        )

    if contract_end is not None and operational_date > contract_end:
        return _result(
            status=ContractDateEligibilityStatus.INELIGIBLE,
            operational_date=operational_date,
            contract_start=contract_start,
            contract_end=contract_end,
            reason_code="after-contract-end",
            reason_message="The operational date follows the contract end.",
        )

    return _result(
        status=ContractDateEligibilityStatus.ELIGIBLE,
        operational_date=operational_date,
        contract_start=contract_start,
        contract_end=contract_end,
        reason_code="contract-date-valid",
        reason_message="The operational date satisfies the known contract limits.",
    )
