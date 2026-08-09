from app.plugins.dsp_quality.domain.models import (
    QualityMappingStatus,
    WorkforceExternalIdentity,
)
from app.plugins.dsp_quality.infrastructure import repository


AMAZON_TRANSPORTER_SOURCE = "amazon_transporter"


class MappingConflictError(ValueError):
    pass


class MappingNotFoundError(ValueError):
    pass


def set_workforce_external_identity(
    *,
    organization_id: str,
    external_id: str,
    status: QualityMappingStatus,
    workforce_member_id: int | None,
    actor: str,
    source: str = AMAZON_TRANSPORTER_SOURCE,
    valid_from: str | None = None,
    valid_to: str | None = None,
) -> WorkforceExternalIdentity:
    organization_id = organization_id.strip()
    source = source.strip()
    external_id = external_id.strip()
    actor = actor.strip()
    if not all((organization_id, source, external_id, actor)):
        raise ValueError("Organization, source, external ID and actor are required.")
    if status is QualityMappingStatus.MATCHED and workforce_member_id is None:
        raise ValueError("MATCHED mappings require a Workforce member.")
    if status is not QualityMappingStatus.MATCHED and workforce_member_id is not None:
        raise ValueError("Only MATCHED mappings can reference Workforce.")
    row = repository.save_external_identity(
        organization_id=organization_id,
        source=source,
        external_id=external_id,
        status=status,
        workforce_member_id=workforce_member_id,
        actor=actor,
        valid_from=valid_from,
        valid_to=valid_to,
    )
    return WorkforceExternalIdentity.model_validate(row)


def resolve_workforce_external_identity(
    *,
    organization_id: str,
    external_id: str,
    source: str = AMAZON_TRANSPORTER_SOURCE,
) -> WorkforceExternalIdentity | None:
    row = repository.find_external_identity(
        organization_id.strip(),
        source.strip(),
        external_id.strip(),
    )
    return WorkforceExternalIdentity.model_validate(row) if row else None


def reconcile_transporter_identity(
    *,
    organization_id: str,
    external_id: str,
    workforce_member_id: int,
    actor: str,
    expected_updated_at: str | None,
) -> dict:
    organization_id = organization_id.strip()
    external_id = external_id.strip()
    actor = actor.strip()
    if not organization_id or not external_id or not actor:
        raise ValueError("Organization, Transporter ID e actor sono obbligatori.")
    try:
        return repository.reconcile_external_identity(
            organization_id=organization_id,
            external_id=external_id,
            workforce_member_id=workforce_member_id,
            actor=actor,
            expected_updated_at=expected_updated_at,
        )
    except repository.ConcurrentMappingUpdateError as exc:
        raise MappingConflictError(str(exc)) from exc
    except repository.MappingNotFoundError as exc:
        raise MappingNotFoundError(str(exc)) from exc


def remove_transporter_identity(
    *,
    organization_id: str,
    external_id: str,
    actor: str,
    expected_updated_at: str,
) -> dict:
    try:
        return repository.remove_external_identity(
            organization_id=organization_id.strip(),
            external_id=external_id.strip(),
            actor=actor.strip(),
            expected_updated_at=expected_updated_at,
        )
    except repository.ConcurrentMappingUpdateError as exc:
        raise MappingConflictError(str(exc)) from exc
    except repository.MappingNotFoundError as exc:
        raise MappingNotFoundError(str(exc)) from exc
