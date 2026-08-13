import json

from app.plugins.workforce.domain.models import (
    WorkforceChange,
    WorkforceDayStatus,
    WorkforceMember,
    WorkforceRequirement,
)


def member_from_row(row) -> WorkforceMember:
    keys = set(row.keys())
    display_name = row["display_name"]
    name_parts = display_name.strip().split(maxsplit=1)
    return WorkforceMember(
        workforce_member_id=int(row["id"]),
        external_identifier=row["external_identifier"],
        display_name=display_name,
        first_name=(row["first_name"] if "first_name" in keys else None) or name_parts[0],
        last_name=(row["last_name"] if "last_name" in keys else None) or (name_parts[1] if len(name_parts) > 1 else ""),
        role=row["role"],
        station=row["station"] if "station" in keys else None,
        employment_type=row["employment_type"],
        operational_cycle=(
            row["operational_cycle"]
            if "operational_cycle" in keys and row["operational_cycle"]
            else "NOT_SET"
        ),
        contract_start=row["contract_start"],
        contract_end=row["contract_end"],
        weekly_hours=row["weekly_hours"],
        capabilities=json.loads(row["capabilities"]),
        operational_notes=row["operational_notes"] if "operational_notes" in keys else None,
        phone=row["phone"] if "phone" in keys else None,
        email=row["email"] if "email" in keys else None,
        is_reserve=bool(row["is_reserve"]) if "is_reserve" in keys else False,
        active=bool(row["active"]),
        source_reference=row["source_reference"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        organization_id=row["organization_id"] if "organization_id" in keys else "default",
    )


def status_from_row(row) -> WorkforceDayStatus:
    keys = set(row.keys())
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
        organization_id=row["organization_id"] if "organization_id" in keys else "default",
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
