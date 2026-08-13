from app.core.database import db_session
from app.plugins.workforce.domain.day_member_batch import (
    DayMemberBatchResult,
    DayMemberBatchWarning,
    DayMemberOverwritePolicy,
)
from app.plugins.workforce.domain.errors import (
    WorkforceDayMemberBatchConflictError,
    WorkforceMemberNotFoundError,
)
from app.plugins.workforce.infrastructure.records import status_from_row
from app.plugins.workforce.infrastructure.write_repository import _save_batch_status
from app.utils.date_utils import utc_now_iso


PROTECTED_STATUS_CODES = frozenset({
    "holiday", "sickness", "leave", "rest", "unavailable"
})


def _placeholders(values: list[int]) -> str:
    return ", ".join("?" for _ in values)


def apply(
    *,
    member_ids: list[int],
    operational_date: str,
    values: dict[str, object],
    overwrite_policy: DayMemberOverwritePolicy,
    confirm_overwrite: bool,
    confirm_unavailable_override: bool,
    actor: str,
    organization_id: str,
) -> DayMemberBatchResult:
    now = utc_now_iso()
    placeholders = _placeholders(member_ids)
    with db_session() as conn:
        members = conn.execute(
            f"""
            SELECT id FROM workforce_members
            WHERE organization_id = ? AND id IN ({placeholders})
            """,
            (organization_id, *member_ids),
        ).fetchall()
        found_ids = {int(row["id"]) for row in members}
        missing_ids = sorted(set(member_ids) - found_ids)
        if missing_ids:
            raise WorkforceMemberNotFoundError(
                "Uno o piu driver Workforce non appartengono all'organizzazione."
            )

        existing_rows = conn.execute(
            f"""
            SELECT * FROM workforce_day_statuses
            WHERE organization_id = ? AND date = ?
              AND workforce_member_id IN ({placeholders})
            """,
            (organization_id, operational_date, *member_ids),
        ).fetchall()
        existing = {int(row["workforce_member_id"]): row for row in existing_rows}
        protected = [
            member_id for member_id, row in existing.items()
            if row["status_code"] in PROTECTED_STATUS_CODES
        ]

        if (
            overwrite_policy == DayMemberOverwritePolicy.REPLACE_SELECTED
            and existing
            and not confirm_overwrite
        ):
            raise WorkforceDayMemberBatchConflictError(
                "La selezione contiene turni o stati gia presenti.",
                {
                    "existing_count": len(existing),
                    "protected_count": len(protected),
                    "member_ids": sorted(existing),
                },
            )
        if (
            overwrite_policy == DayMemberOverwritePolicy.REPLACE_SELECTED
            and protected
            and not confirm_unavailable_override
        ):
            raise WorkforceDayMemberBatchConflictError(
                "La selezione contiene ferie, riposi o assenze da confermare.",
                {
                    "existing_count": len(existing),
                    "protected_count": len(protected),
                    "member_ids": sorted(protected),
                },
            )

        skipped_ids = (
            set(existing)
            if overwrite_policy == DayMemberOverwritePolicy.APPLY_TO_EMPTY_ONLY
            else set()
        )
        rows = []
        for member_id in member_ids:
            if member_id in skipped_ids:
                continue
            rows.append(_save_batch_status(
                conn,
                {
                    **values,
                    "workforce_member_id": member_id,
                    "date": operational_date,
                },
                actor,
                organization_id,
                now,
                reason="manual_day_member_batch_update",
                source="manual_day_planning",
            ))

    warnings = [
        DayMemberBatchWarning(
            workforce_member_id=member_id,
            code="EXISTING_STATUS_SKIPPED",
            message="Turno o stato esistente non modificato.",
            existing_status_code=str(existing[member_id]["status_code"]),
        )
        for member_id in sorted(skipped_ids)
    ]
    return DayMemberBatchResult(
        operational_date=operational_date,
        overwrite_policy=overwrite_policy,
        requested_count=len(member_ids),
        applied_count=len(rows),
        skipped_count=len(skipped_ids),
        overwritten_count=sum(member_id in existing for member_id in member_ids if member_id not in skipped_ids),
        items=[status_from_row(row) for row in rows],
        warnings=warnings,
    )
