import json

from app.plugins.workforce.domain.models import (
    WorkforceChange,
    WorkforceDayStatus,
    WorkforceMember,
    WorkforceRequirement,
)


def member_from_row(row) -> WorkforceMember:
    return WorkforceMember(
        workforce_member_id=int(row["id"]),
        external_identifier=row["external_identifier"],
        display_name=row["display_name"],
        role=row["role"],
        employment_type=row["employment_type"],
        contract_start=row["contract_start"],
        contract_end=row["contract_end"],
        weekly_hours=row["weekly_hours"],
        capabilities=json.loads(row["capabilities"]),
        active=bool(row["active"]),
        source_reference=row["source_reference"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def status_from_row(row) -> WorkforceDayStatus:
    return WorkforceDayStatus(
        status_id=int(row["id"]),
        workforce_member_id=int(row["workforce_member_id"]),
        date=row["date"],
        status_code=row["status_code"],
        availability=bool(row["availability"]),
        shift_code=row["shift_code"],
        start_time=row["start_time"],
        end_time=row["end_time"],
        notes=row["notes"],
        source_reference=row["source_reference"],
        observed_or_confirmed=row["observed_or_confirmed"],
        updated_at=row["updated_at"],
    )


def requirement_from_row(row) -> WorkforceRequirement:
    return WorkforceRequirement(
        requirement_id=int(row["id"]),
        date=row["date"],
        operational_unit_id=row["operational_unit_id"],
        required_resources=int(row["required_resources"]),
        required_capabilities=json.loads(row["required_capabilities"]),
        source=row["source"],
        version=int(row["version"]),
    )


def change_from_row(row) -> WorkforceChange:
    return WorkforceChange(
        change_id=int(row["id"]),
        entity_type=row["entity_type"],
        entity_id=row["entity_id"],
        actor=row["actor"],
        timestamp=row["timestamp"],
        before=(json.loads(row["before_value"]) if row["before_value"] else None),
        after=json.loads(row["after_value"]),
        reason=row["reason"],
        source=row["source"],
    )
