from datetime import date
from decimal import Decimal
from inspect import signature
from pathlib import Path

from app.domain.core_language import HumanResource, OperationalUnit, TimeWindow
from app.domain.workforce_auto_planning import (
    AssignedTimeSnapshot,
    AssignedTimeUnit,
    CurrentMemberContractStateSnapshot,
    OperationalDemand,
    OperationalDemandProvider,
    WorkforceCandidateSnapshot,
    WorkforceCandidateSnapshotProvider,
)


class GenericDemandProvider:
    def __init__(self, demands: tuple[OperationalDemand, ...]):
        self.demands = demands
        self.request = None

    def get_demands(
        self,
        *,
        organization_id: str,
        period_start: date,
        period_end: date,
        operational_unit: OperationalUnit,
    ) -> tuple[OperationalDemand, ...]:
        self.request = (
            organization_id,
            period_start,
            period_end,
            operational_unit,
        )
        return self.demands


class GenericCandidateProvider:
    def __init__(self, candidates: tuple[WorkforceCandidateSnapshot, ...]):
        self.candidates = candidates
        self.request = None

    def get_candidates(
        self,
        *,
        organization_id: str,
        period_start: date,
        period_end: date,
        operational_unit: OperationalUnit,
    ) -> tuple[WorkforceCandidateSnapshot, ...]:
        self.request = (
            organization_id,
            period_start,
            period_end,
            operational_unit,
        )
        return self.candidates


START = date(2026, 8, 17)
END = date(2026, 8, 23)
UNIT = OperationalUnit(external_identifier="unit-north")
WINDOW = TimeWindow(external_identifier="open-window")


def _demand() -> OperationalDemand:
    return OperationalDemand(
        organization_id="org-1",
        operational_unit=UNIT,
        date=START,
        time_window=WINDOW,
        capability_or_workload="parcel-delivery",
        base_quantity=5,
        target_quantity=5,
        source="generic-forecast",
    )


def _candidate() -> WorkforceCandidateSnapshot:
    return WorkforceCandidateSnapshot(
        organization_id="org-1",
        human_resource=HumanResource(
            external_identifier="member-1",
            capabilities=("parcel-delivery",),
        ),
        applicable_contract_state=CurrentMemberContractStateSnapshot(),
        recent_consecutivity=0,
        already_assigned_minutes_or_hours=AssignedTimeSnapshot(
            value=Decimal("0"), unit=AssignedTimeUnit.MINUTES
        ),
    )


def test_generic_providers_satisfy_the_neutral_runtime_contracts():
    demand_provider = GenericDemandProvider((_demand(),))
    candidate_provider = GenericCandidateProvider((_candidate(),))

    assert isinstance(demand_provider, OperationalDemandProvider)
    assert isinstance(candidate_provider, WorkforceCandidateSnapshotProvider)


def test_demand_provider_scope_is_explicit_and_returns_core_demands():
    provider = GenericDemandProvider((_demand(),))

    result = provider.get_demands(
        organization_id="org-1",
        period_start=START,
        period_end=END,
        operational_unit=UNIT,
    )

    assert provider.request == ("org-1", START, END, UNIT)
    assert isinstance(result, tuple)
    assert all(isinstance(item, OperationalDemand) for item in result)


def test_candidate_provider_scope_is_explicit_and_returns_core_candidates():
    provider = GenericCandidateProvider((_candidate(),))

    result = provider.get_candidates(
        organization_id="org-1",
        period_start=START,
        period_end=END,
        operational_unit=UNIT,
    )

    assert provider.request == ("org-1", START, END, UNIT)
    assert isinstance(result, tuple)
    assert all(isinstance(item, WorkforceCandidateSnapshot) for item in result)


def test_both_port_signatures_require_the_full_weekly_scope():
    expected = {
        "organization_id",
        "period_start",
        "period_end",
        "operational_unit",
    }

    demand_parameters = set(signature(OperationalDemandProvider.get_demands).parameters)
    candidate_parameters = set(
        signature(WorkforceCandidateSnapshotProvider.get_candidates).parameters
    )

    assert expected <= demand_parameters
    assert expected <= candidate_parameters


def test_contracts_are_neutral_and_do_not_import_runtime_layers():
    contract_file = (
        Path(__file__).parents[1]
        / "app"
        / "domain"
        / "workforce_auto_planning"
        / "snapshot_provider_ports.py"
    )
    source = contract_file.read_text(encoding="utf-8").lower()

    forbidden_terms = (
        "amazon",
        "dsp",
        "next_day",
        "same_day",
        "fleet",
        "vehicle",
        "plugins.workforce",
        "infrastructure",
        "repository",
        "database",
    )
    assert all(term not in source for term in forbidden_terms)
