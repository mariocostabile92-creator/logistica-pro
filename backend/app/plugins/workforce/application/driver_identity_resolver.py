from app.plugins.workforce.domain.driver_identity import (
    DriverIdentityResolution,
    DriverIdentityResolutionStatus,
    DriverIdentitySource,
)
from app.plugins.workforce.infrastructure import read_repository


MAX_IDENTIFIER_LENGTH = 200


def _invalid(source: str, identifier: str | None) -> DriverIdentityResolution:
    return DriverIdentityResolution(
        status=DriverIdentityResolutionStatus.INVALID,
        matched=False,
        source=source,
        driver_identifier=identifier,
    )


def resolve_driver_identity(
    *,
    organization_id: str,
    driver_identifier: str | None,
    source: str,
) -> DriverIdentityResolution:
    normalized_source = str(source or "").strip().casefold()
    normalized_organization = str(organization_id or "").strip()
    normalized_identifier = (
        driver_identifier.strip()
        if isinstance(driver_identifier, str)
        else None
    )
    if (
        normalized_source not in {item.value for item in DriverIdentitySource}
        or not normalized_organization
        or not normalized_identifier
        or len(normalized_identifier) > MAX_IDENTIFIER_LENGTH
    ):
        return _invalid(normalized_source, normalized_identifier)

    candidates = read_repository.find_members_by_external_identifier(
        normalized_organization,
        normalized_identifier,
    )
    if not candidates:
        return DriverIdentityResolution(
            status=DriverIdentityResolutionStatus.NOT_FOUND,
            matched=False,
            source=normalized_source,
            driver_identifier=normalized_identifier,
        )
    if len(candidates) > 1:
        return DriverIdentityResolution(
            status=DriverIdentityResolutionStatus.AMBIGUOUS,
            matched=False,
            source=normalized_source,
            driver_identifier=normalized_identifier,
            candidate_count=len(candidates),
        )

    member = candidates[0]
    return DriverIdentityResolution(
        status=DriverIdentityResolutionStatus.MATCH,
        matched=True,
        source=normalized_source,
        driver_identifier=normalized_identifier,
        workforce_member_id=member.workforce_member_id,
        external_identifier=member.external_identifier,
        display_name=member.display_name,
        candidate_count=1,
    )
