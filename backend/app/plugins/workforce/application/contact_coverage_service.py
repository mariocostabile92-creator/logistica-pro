from app.plugins.workforce.domain.contact_coverage import WorkforceContactCoverage
from app.plugins.workforce.domain.driver_shift_contact import (
    normalize_email,
    normalize_phone,
)
from app.plugins.workforce.infrastructure.contact_coverage_repository import (
    contact_coverage_rows,
)


def _counts(rows: list[dict[str, object]]) -> dict[str, int]:
    result = {
        "phone_valid": 0,
        "phone_invalid": 0,
        "phone_missing": 0,
        "email_valid": 0,
        "email_invalid": 0,
        "email_missing": 0,
        "both_valid": 0,
        "no_channel": 0,
    }
    for row in rows:
        raw_phone = str(row.get("phone") or "").strip()
        raw_email = str(row.get("email") or "").strip()
        phone = normalize_phone(raw_phone)
        email = normalize_email(raw_email)
        result[
            "phone_valid" if phone
            else "phone_invalid" if raw_phone
            else "phone_missing"
        ] += 1
        result[
            "email_valid" if email
            else "email_invalid" if raw_email
            else "email_missing"
        ] += 1
        result["both_valid"] += bool(phone and email)
        result["no_channel"] += not phone and not email
    return result


def contact_coverage(organization_id: str) -> WorkforceContactCoverage:
    rows = contact_coverage_rows(organization_id)
    members = rows["members"]
    planning = rows["planning"]
    recipients = rows["recipients"]
    member_counts = _counts(members)
    values: dict[str, object] = {
        "total_members": len(members),
        "active_members": sum(bool(item["active"]) for item in members),
        **member_counts,
        "active_planning_available": planning is not None,
        "active_planning_id": int(planning["id"]) if planning else None,
    }
    if planning is not None:
        recipient_counts = _counts(recipients)
        values.update({
            "recipients_total": len(recipients),
            "recipients_phone_ready": recipient_counts["phone_valid"],
            "recipients_email_ready": recipient_counts["email_valid"],
            "recipients_both": recipient_counts["both_valid"],
            "recipients_no_channel": recipient_counts["no_channel"],
        })
    return WorkforceContactCoverage.model_validate(values)
