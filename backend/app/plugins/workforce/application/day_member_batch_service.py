from app.plugins.workforce.application.workforce_service import _normalized_day_status
from app.plugins.workforce.domain.day_member_batch import (
    DayMemberBatchResult,
    DayMemberOverwritePolicy,
)
from app.plugins.workforce.domain.errors import WorkforceValidationError
from app.plugins.workforce.infrastructure import day_member_batch_repository


def apply(
    values: dict[str, object],
    actor: str,
    organization_id: str,
) -> DayMemberBatchResult:
    member_ids = [int(value) for value in values.pop("workforce_member_ids", [])]
    if not member_ids or len(member_ids) != len(set(member_ids)):
        raise WorkforceValidationError("I driver selezionati non sono validi.")

    operational_date = str(values.pop("operational_date", ""))
    overwrite_policy = DayMemberOverwritePolicy(
        values.pop("overwrite_policy", DayMemberOverwritePolicy.APPLY_TO_EMPTY_ONLY)
    )
    confirm_overwrite = bool(values.pop("confirm_overwrite", False))
    confirm_unavailable_override = bool(
        values.pop("confirm_unavailable_override", False)
    )
    values["_operational_activity_provided"] = "operational_activity" in values
    normalized = _normalized_day_status(values)
    return day_member_batch_repository.apply(
        member_ids=member_ids,
        operational_date=operational_date,
        values=normalized,
        overwrite_policy=overwrite_policy,
        confirm_overwrite=confirm_overwrite,
        confirm_unavailable_override=confirm_unavailable_override,
        actor=actor,
        organization_id=organization_id,
    )
