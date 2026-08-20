from dataclasses import replace

import pytest
from pydantic import ValidationError

from app.core.database import db_session
from app.plugins.workforce.domain.coverage import (
    CoverageSource,
    ForecastAuthorityStatus,
    ImportedDailyCoverageRequirement,
)
from app.plugins.workforce.infrastructure import coverage_repository
from app.utils.date_utils import utc_now_iso


ORG_A = "coverage-reader-org-a"
ORG_B = "coverage-reader-org-b"
DATE = "2026-08-15"


def _requirement(
    forecast_routes: int,
    *,
    source_identity: str,
    source: str = CoverageSource.IMPORT.value,
    authority_status: str = ForecastAuthorityStatus.AUTHORITATIVE.value,
    detection_reason: str | None = None,
    cycle: str = "NEXT_DAY",
    segment: str | None = None,
    station: str | None = None,
) -> ImportedDailyCoverageRequirement:
    return ImportedDailyCoverageRequirement(
        operational_date=DATE,
        station=station,
        operational_cycle=cycle,
        coverage_segment=segment,
        forecast_routes=forecast_routes,
        reserve_percentage=99,
        required_capacity=999,
        source=source,
        source_reference="source-cell-not-exposed",
        source_identity=source_identity,
        authority_status=authority_status,
        detection_reason=detection_reason,
    )


def _persist(
    organization_id: str,
    requirements: list[ImportedDailyCoverageRequirement],
) -> None:
    with db_session() as conn:
        coverage_repository.persist_imported_requirements(
            conn,
            requirements,
            organization_id=organization_id,
            now=utc_now_iso(),
        )


def _read(organization_id: str = ORG_A):
    return coverage_repository.list_effective_coverage_demands(
        organization_id,
        DATE,
        DATE,
    )


def test_raw_forecast_and_provenance_are_preserved_without_capacity_fields():
    _persist(ORG_A, [_requirement(12, source_identity="import:raw")])

    row = _read()[0]

    assert row.forecast_routes == 12
    assert row.source == CoverageSource.IMPORT.value
    assert row.source_identity == "import:raw"
    assert not hasattr(row, "required_capacity")
    assert not hasattr(row, "reserve_percentage")


def test_manual_planning_input_has_existing_precedence_over_import():
    imported = _requirement(100, source_identity="import:first")
    manual = replace(
        imported,
        forecast_routes=70,
        source=CoverageSource.MANUAL_PLANNING_INPUT.value,
        source_identity="manual-planning:override",
    )
    _persist(ORG_A, [imported, manual])

    rows = _read()

    assert len(rows) == 1
    assert rows[0].forecast_routes == 70
    assert rows[0].source == CoverageSource.MANUAL_PLANNING_INPUT.value


def test_manual_has_existing_precedence_over_import():
    imported = _requirement(100, source_identity="import:first")
    manual = replace(
        imported,
        forecast_routes=80,
        source=CoverageSource.MANUAL.value,
        source_identity="manual:override",
    )
    _persist(ORG_A, [imported, manual])

    rows = _read()

    assert len(rows) == 1
    assert rows[0].forecast_routes == 80
    assert rows[0].source == CoverageSource.MANUAL.value


def test_rejected_template_is_not_exposed_but_remains_in_legacy_reader():
    rejected = _requirement(
        55,
        source_identity="import:rejected",
        authority_status=ForecastAuthorityStatus.REJECTED_TEMPLATE.value,
        detection_reason="LONG_ARITHMETIC_SEQUENCE",
    )
    _persist(ORG_A, [rejected])

    legacy = coverage_repository.list_current_requirements(
        ORG_A,
        DATE,
        DATE,
    )

    assert len(legacy) == 1
    assert legacy[0].authority_status is ForecastAuthorityStatus.REJECTED_TEMPLATE
    assert _read() == ()


def test_suspect_template_remains_effective_with_authority_evidence():
    suspect = _requirement(
        21,
        source_identity="import:suspect",
        authority_status=ForecastAuthorityStatus.SUSPECT_TEMPLATE.value,
        detection_reason="CORRELATED_CONSTANT_BLOCK",
        cycle="SAME_DAY",
        segment="A",
    )
    _persist(ORG_A, [suspect])

    row = _read()[0]

    assert row.forecast_routes == 21
    assert row.authority_status is ForecastAuthorityStatus.SUSPECT_TEMPLATE
    assert row.detection_reason == "CORRELATED_CONSTANT_BLOCK"


def test_same_logical_bucket_exposes_only_the_selected_effective_source():
    first = _requirement(10, source_identity="import:one")
    second = _requirement(20, source_identity="import:two")
    _persist(ORG_A, [first, second])

    rows = _read()

    assert len(rows) == 1
    assert rows[0].forecast_routes == 20
    assert rows[0].source_identity == "import:two"


@pytest.mark.parametrize("station", [None, "station-north"])
def test_station_is_preserved_without_binding_or_fallback(station):
    _persist(
        ORG_A,
        [_requirement(10, source_identity=f"import:{station}", station=station)],
    )

    assert _read()[0].station == station


def test_organization_isolation_is_explicit():
    _persist(ORG_A, [_requirement(10, source_identity="import:org-a")])
    _persist(ORG_B, [_requirement(20, source_identity="import:org-b")])

    first = _read(ORG_A)
    second = _read(ORG_B)

    assert {row.organization_id for row in first} == {ORG_A}
    assert {row.organization_id for row in second} == {ORG_B}
    assert first[0].forecast_routes == 10
    assert second[0].forecast_routes == 20


@pytest.mark.parametrize("organization_id", ["", "   ", None])
def test_organization_id_is_required(organization_id):
    with pytest.raises(ValueError, match="organization_id"):
        coverage_repository.list_effective_coverage_demands(
            organization_id,
            DATE,
            DATE,
        )


def test_invalid_period_is_rejected():
    with pytest.raises(ValueError, match="period_end"):
        coverage_repository.list_effective_coverage_demands(
            ORG_A,
            "2026-08-16",
            "2026-08-15",
        )


def test_reader_calls_current_requirement_batch_once_and_never_assigned_groups(
    monkeypatch,
):
    _persist(ORG_A, [_requirement(12, source_identity="import:batch")])
    original = coverage_repository.list_current_requirements
    calls: list[tuple[object, ...]] = []

    def current_spy(*args, **kwargs):
        calls.append((*args, kwargs))
        return original(*args, **kwargs)

    def assigned_forbidden(*_args, **_kwargs):
        raise AssertionError("assigned drivers must not be queried")

    monkeypatch.setattr(
        coverage_repository,
        "list_current_requirements",
        current_spy,
    )
    monkeypatch.setattr(
        coverage_repository,
        "assigned_driver_groups",
        assigned_forbidden,
    )

    rows = _read()

    assert len(rows) == 1
    assert len(calls) == 1
    assert calls[0][:3] == (ORG_A, DATE, DATE)


def test_effective_row_is_immutable():
    _persist(ORG_A, [_requirement(12, source_identity="import:immutable")])
    row = _read()[0]

    with pytest.raises(ValidationError):
        row.forecast_routes = 99
