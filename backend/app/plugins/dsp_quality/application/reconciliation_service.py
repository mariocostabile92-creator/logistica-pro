from app.plugins.dsp_quality.application.drivers_read_service import get_latest_drivers
from app.plugins.dsp_quality.application.mapping_service import (
    MappingConflictError,
    reconcile_transporter_identity,
    remove_transporter_identity,
)
from app.plugins.dsp_quality.application.reconciliation_models import (
    MappingHistory,
    MappingHistoryItem,
    MappingWriteResult,
    ReconciliationRow,
    ReconciliationState,
    ReconciliationSummary,
    WorkforceCandidate,
    WorkforceCandidateList,
)
from app.plugins.dsp_quality.infrastructure import reconciliation_repository
from app.plugins.workforce.infrastructure import read_repository as workforce_repository


class ReconciliationNotFoundError(ValueError):
    pass


def _exact_transporter(organization_id: str, external_id: str):
    snapshot = get_latest_drivers(organization_id)
    match = next(
        (row for row in snapshot.rows if row.transporter_external_id == external_id),
        None,
    )
    if not match:
        raise ReconciliationNotFoundError(
            "Transporter non presente nella scorecard attiva dell'organizzazione."
        )
    return match


def reconciliation_state(organization_id: str) -> ReconciliationState:
    snapshot = get_latest_drivers(organization_id)
    if not snapshot.available:
        return ReconciliationState(available=False)
    metadata = reconciliation_repository.identity_metadata(
        organization_id,
        [row.transporter_external_id for row in snapshot.rows],
    )
    rows = []
    for row in snapshot.rows:
        current = metadata.get(row.transporter_external_id, {})
        delivered = next(
            (
                metric.current.raw_value
                for metric in row.metrics
                if metric.metric_key == "delivered"
            ),
            None,
        )
        rows.append(ReconciliationRow(
            transporter_external_id=row.transporter_external_id,
            mapping_status=row.mapping_status,
            workforce_member_id=row.workforce_member_id,
            workforce_display_name=row.workforce_display_name,
            delivered=delivered,
            verified_at=current.get("verified_at"),
            verified_by=current.get("verified_by"),
            updated_at=current.get("updated_at"),
        ))
    return ReconciliationState(
        available=True,
        week=snapshot.current_period.week,
        year=snapshot.current_period.year,
        summary=ReconciliationSummary(**snapshot.summary.model_dump()),
        rows=rows,
    )


def search_workforce_candidates(
    organization_id: str,
    query: str,
    limit: int = 20,
) -> WorkforceCandidateList:
    query = query.strip()
    if len(query) < 2:
        return WorkforceCandidateList()
    members = workforce_repository.search_members(
        organization_id,
        query,
        limit=limit,
    )
    return WorkforceCandidateList(items=[
        WorkforceCandidate(
            workforce_member_id=member.workforce_member_id,
            display_name=member.display_name,
            external_identifier=member.external_identifier,
            station=member.station,
            contract=member.employment_type,
            active=member.active,
        )
        for member in members
    ])


def put_mapping(
    *,
    organization_id: str,
    external_id: str,
    workforce_member_id: int,
    actor: str,
    expected_updated_at: str | None,
) -> MappingWriteResult:
    _exact_transporter(organization_id, external_id)
    row = reconcile_transporter_identity(
        organization_id=organization_id,
        external_id=external_id,
        workforce_member_id=workforce_member_id,
        actor=actor,
        expected_updated_at=expected_updated_at,
    )
    return MappingWriteResult(
        transporter_external_id=external_id,
        mapping_status="MATCHED",
        workforce_member_id=row["workforce_member_id"],
        workforce_display_name=row["workforce_display_name"],
        verified_at=row["verified_at"],
        verified_by=row["verified_by"],
        updated_at=row["updated_at"],
    )


def delete_mapping(
    *,
    organization_id: str,
    external_id: str,
    actor: str,
    expected_updated_at: str,
) -> MappingWriteResult:
    _exact_transporter(organization_id, external_id)
    row = remove_transporter_identity(
        organization_id=organization_id,
        external_id=external_id,
        actor=actor,
        expected_updated_at=expected_updated_at,
    )
    return MappingWriteResult(
        transporter_external_id=external_id,
        mapping_status="UNMAPPED",
        workforce_member_id=None,
        workforce_display_name=None,
        verified_at=row["verified_at"],
        verified_by=row["verified_by"],
        updated_at=row["updated_at"],
    )


def mapping_history(organization_id: str, external_id: str) -> MappingHistory:
    _exact_transporter(organization_id, external_id)
    return MappingHistory(
        transporter_external_id=external_id,
        items=[
            MappingHistoryItem.model_validate(item)
            for item in reconciliation_repository.history(organization_id, external_id)
        ],
    )


__all__ = [
    "MappingConflictError",
    "ReconciliationNotFoundError",
    "delete_mapping",
    "mapping_history",
    "put_mapping",
    "reconciliation_state",
    "search_workforce_candidates",
]
