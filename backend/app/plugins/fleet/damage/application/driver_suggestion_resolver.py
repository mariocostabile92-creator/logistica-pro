from datetime import date

from app.plugins.fleet.damage.domain.driver_suggestion import (
    DriverSuggestionCandidate,
    DriverSuggestionResolution,
    DriverSuggestionStatus,
)
from app.plugins.fleet.journal.control_room import completion_repository
from app.plugins.fleet.journal.control_room.planning_vehicle_adapter import (
    assignment_is_active,
    fleet_asset_for_assignment,
    index_fleet_assets_by_plate,
)
from app.plugins.fleet.journal.infrastructure import repository as journal_repository
from app.plugins.workforce.application.driver_identity_resolver import (
    resolve_driver_identity,
)
from app.plugins.workforce.domain.driver_identity import (
    DriverIdentityResolutionStatus,
)


def _candidate(
    resolution,
    source: str,
    evidence: tuple[str, ...],
) -> DriverSuggestionCandidate:
    return DriverSuggestionCandidate(
        workforce_member_id=resolution.workforce_member_id,
        external_identifier=resolution.external_identifier,
        display_name=resolution.display_name,
        source=source,
        evidence=evidence,
    )


def _resolve_evidence(
    *,
    organization_id: str,
    source: str,
    evidence_by_identifier: dict[str, list[str]],
) -> tuple[DriverSuggestionCandidate | None, bool, tuple[str, ...]]:
    identities: dict[int, DriverSuggestionCandidate] = {}
    unresolved = 0
    all_evidence = tuple(
        reference
        for references in evidence_by_identifier.values()
        for reference in references
    )
    for identifier, references in evidence_by_identifier.items():
        resolution = resolve_driver_identity(
            organization_id=organization_id,
            driver_identifier=identifier,
            source=source,
        )
        if resolution.status is DriverIdentityResolutionStatus.AMBIGUOUS:
            return None, True, all_evidence
        if resolution.status is not DriverIdentityResolutionStatus.MATCH:
            unresolved += 1
            continue
        candidate = _candidate(resolution, source, tuple(references))
        current = identities.get(candidate.workforce_member_id)
        if current:
            identities[candidate.workforce_member_id] = current.model_copy(
                update={"evidence": current.evidence + candidate.evidence}
            )
        else:
            identities[candidate.workforce_member_id] = candidate
    if (
        len(identities) > 1
        or (identities and unresolved)
        or (not identities and unresolved > 1)
    ):
        return None, True, all_evidence
    if not identities:
        return None, False, all_evidence
    return next(iter(identities.values())), False, all_evidence


def _journal_driver(
    history: dict,
    organization_id: str,
    operational_date: str,
) -> tuple[DriverSuggestionCandidate | None, bool, tuple[str, ...]]:
    evidence: dict[str, list[str]] = {}
    for movement in history.get("movements", []):
        if str(movement.get("operational_date") or "") != operational_date:
            continue
        identifier = str(movement.get("declared_driver_identifier") or "").strip()
        key = identifier.casefold()
        evidence.setdefault(key, []).append(f"journal:movement:{movement['id']}")
    identifiers = {
        next(
            str(movement.get("declared_driver_identifier") or "").strip()
            for movement in history.get("movements", [])
            if str(movement.get("operational_date") or "") == operational_date
            and str(movement.get("declared_driver_identifier") or "").strip().casefold() == key
        ): references
        for key, references in evidence.items()
    }
    return _resolve_evidence(
        organization_id=organization_id,
        source="journal",
        evidence_by_identifier=identifiers,
    )


def _planning_driver(
    *,
    organization_id: str,
    vehicle_id: int,
    operational_date: str,
) -> tuple[DriverSuggestionCandidate | None, bool, tuple[str, ...]]:
    snapshot = completion_repository.authoritative_planning_snapshot(
        operational_date,
        organization_id,
    )
    if not snapshot:
        return None, False, ()
    assets = index_fleet_assets_by_plate(snapshot["assets"])
    evidence: dict[str, list[str]] = {}
    for assignment in snapshot["assignments"]:
        if not assignment_is_active(assignment):
            continue
        asset = fleet_asset_for_assignment(assignment, assets)
        if not asset or int(asset["id"]) != vehicle_id:
            continue
        identifier = str(assignment.get("driver_id") or "").strip()
        if not identifier:
            continue
        evidence.setdefault(identifier.casefold(), []).append(
            "planning:"
            f"{snapshot['planning']['id']}:"
            f"{snapshot['planning']['status']}:"
            f"assignment:{assignment['id']}"
        )
    identifiers = {
        next(
            str(assignment.get("driver_id") or "").strip()
            for assignment in snapshot["assignments"]
            if str(assignment.get("driver_id") or "").strip().casefold() == key
        ): references
        for key, references in evidence.items()
    }
    return _resolve_evidence(
        organization_id=organization_id,
        source="planning",
        evidence_by_identifier=identifiers,
    )


def _match(
    selected: DriverSuggestionCandidate,
    *,
    journal_driver: DriverSuggestionCandidate | None,
    planning_driver: DriverSuggestionCandidate | None,
) -> DriverSuggestionResolution:
    return DriverSuggestionResolution(
        status=DriverSuggestionStatus.MATCH,
        matched=True,
        source=selected.source,
        workforce_member_id=selected.workforce_member_id,
        external_identifier=selected.external_identifier,
        display_name=selected.display_name,
        journal_driver=journal_driver,
        planning_driver=planning_driver,
        evidence=selected.evidence,
    )


def resolve_driver_suggestion(
    *,
    organization_id: str,
    vehicle_id: int,
    operational_date: str,
) -> DriverSuggestionResolution:
    organization_id = str(organization_id or "").strip()
    try:
        parsed_date = date.fromisoformat(str(operational_date or ""))
    except ValueError:
        parsed_date = None
    if (
        not organization_id
        or isinstance(vehicle_id, bool)
        or not isinstance(vehicle_id, int)
        or vehicle_id <= 0
        or parsed_date is None
    ):
        return DriverSuggestionResolution(
            status=DriverSuggestionStatus.INVALID,
            matched=False,
        )
    day = parsed_date.isoformat()
    history = journal_repository.asset_history(vehicle_id, organization_id)
    if not history:
        return DriverSuggestionResolution(
            status=DriverSuggestionStatus.NOT_FOUND,
            matched=False,
        )

    journal_driver, journal_ambiguous, journal_evidence = _journal_driver(
        history,
        organization_id,
        day,
    )
    if journal_ambiguous:
        return DriverSuggestionResolution(
            status=DriverSuggestionStatus.AMBIGUOUS,
            matched=False,
            evidence=journal_evidence,
        )
    planning_driver, planning_ambiguous, planning_evidence = _planning_driver(
        organization_id=organization_id,
        vehicle_id=vehicle_id,
        operational_date=day,
    )
    if planning_ambiguous:
        return DriverSuggestionResolution(
            status=DriverSuggestionStatus.AMBIGUOUS,
            matched=False,
            journal_driver=journal_driver,
            evidence=journal_evidence + planning_evidence,
        )
    if journal_driver and planning_driver:
        if journal_driver.workforce_member_id != planning_driver.workforce_member_id:
            return DriverSuggestionResolution(
                status=DriverSuggestionStatus.CONFLICT,
                matched=False,
                conflict=True,
                journal_driver=journal_driver,
                planning_driver=planning_driver,
                evidence=journal_driver.evidence + planning_driver.evidence,
            )
        return _match(
            journal_driver,
            journal_driver=journal_driver,
            planning_driver=planning_driver,
        )
    if journal_driver:
        return _match(
            journal_driver,
            journal_driver=journal_driver,
            planning_driver=None,
        )
    if planning_driver:
        return _match(
            planning_driver,
            journal_driver=None,
            planning_driver=planning_driver,
        )
    return DriverSuggestionResolution(
        status=DriverSuggestionStatus.NOT_FOUND,
        matched=False,
        evidence=journal_evidence + planning_evidence,
    )
