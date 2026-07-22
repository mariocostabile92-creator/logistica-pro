from datetime import date, datetime, timedelta

from app.domain.core_language import OperationalUnit
from app.domain.planning_inputs import (
    PlanningInputScope,
    PlanningInputSnapshot,
    PlanningInputStatus,
    compose_planning_input_envelope,
)
from app.runtime.planning_inputs.compatibility import (
    evaluate_planning_input_compatibility,
)
from app.runtime.planning_inputs.contracts import PlanningInputProducer
from app.runtime.planning_inputs.diagnostics import (
    build_planning_input_diagnostics,
)
from app.runtime.planning_inputs.models import (
    PlanningInputCompositionReport,
    PlanningInputCompositionResult,
    PlanningInputRuntimeStatus,
)


_STRUCTURAL_CHECKS = frozenset(
    {
        "WORKFORCE_PRESENT",
        "FLEET_PRESENT",
        "INPUT_TYPES",
        "ORGANIZATION",
        "OPERATIONAL_UNIT",
        "PLANNING_DATE",
        "REQUESTED_SCOPE",
        "VERSION",
        "FRESHNESS",
        "SOURCE",
        "FINGERPRINT",
    }
)
_STATUS_PRIORITY = (
    (PlanningInputStatus.INVALID, PlanningInputRuntimeStatus.INVALID),
    (PlanningInputStatus.MISSING, PlanningInputRuntimeStatus.MISSING),
    (PlanningInputStatus.STALE, PlanningInputRuntimeStatus.STALE),
    (PlanningInputStatus.PARTIAL, PlanningInputRuntimeStatus.PARTIAL),
)


class PlanningInputRuntimeService:
    def __init__(
        self,
        *,
        workforce_producer: PlanningInputProducer,
        fleet_producer: PlanningInputProducer,
        workforce_freshness_ttl: timedelta,
        fleet_freshness_ttl: timedelta,
    ) -> None:
        if workforce_freshness_ttl <= timedelta(0):
            raise ValueError("workforce_freshness_ttl must be positive.")
        if fleet_freshness_ttl <= timedelta(0):
            raise ValueError("fleet_freshness_ttl must be positive.")
        self._workforce_producer = workforce_producer
        self._fleet_producer = fleet_producer
        self._workforce_freshness_ttl = workforce_freshness_ttl
        self._fleet_freshness_ttl = fleet_freshness_ttl

    @staticmethod
    def _request_snapshot(
        label: str,
        producer: PlanningInputProducer,
        *,
        organization_id: str,
        operational_unit: OperationalUnit,
        operation_date: date,
        composed_at: datetime,
        freshness_ttl: timedelta,
    ) -> tuple[PlanningInputSnapshot | None, str | None]:
        try:
            snapshot = producer(
                organization_id=organization_id,
                operational_unit=operational_unit,
                operation_date=operation_date,
                assessed_at=composed_at,
                freshness_ttl=freshness_ttl,
            )
        except Exception:
            return None, f"{label} producer failed."
        if snapshot is not None and not isinstance(
            snapshot, PlanningInputSnapshot
        ):
            return None, f"{label} producer returned an invalid contract."
        return snapshot, None

    @staticmethod
    def _status(
        workforce: PlanningInputSnapshot | None,
        fleet: PlanningInputSnapshot | None,
        compatibility,
    ) -> PlanningInputRuntimeStatus:
        structural_failure = any(
            check.code in _STRUCTURAL_CHECKS
            and check.compatible is not True
            for check in compatibility.checks
        )
        if structural_failure or workforce is None or fleet is None:
            return PlanningInputRuntimeStatus.INCOMPATIBLE
        input_statuses = {
            workforce.validation.status,
            fleet.validation.status,
        }
        for input_status, runtime_status in _STATUS_PRIORITY:
            if input_status in input_statuses:
                return runtime_status
        if compatibility.compatible:
            return PlanningInputRuntimeStatus.READY
        return PlanningInputRuntimeStatus.INCOMPATIBLE

    def compose(
        self,
        *,
        organization_id: str,
        operational_unit: OperationalUnit,
        operation_date: date,
        composed_at: datetime,
    ) -> PlanningInputCompositionResult:
        if composed_at.utcoffset() is None:
            raise ValueError("composed_at must be timezone-aware.")
        workforce, workforce_error = self._request_snapshot(
            "Workforce",
            self._workforce_producer,
            organization_id=organization_id,
            operational_unit=operational_unit,
            operation_date=operation_date,
            composed_at=composed_at,
            freshness_ttl=self._workforce_freshness_ttl,
        )
        fleet, fleet_error = self._request_snapshot(
            "Fleet",
            self._fleet_producer,
            organization_id=organization_id,
            operational_unit=operational_unit,
            operation_date=operation_date,
            composed_at=composed_at,
            freshness_ttl=self._fleet_freshness_ttl,
        )
        expected_scope = PlanningInputScope(
            organization_id=organization_id,
            operational_unit=operational_unit,
            operation_date=operation_date,
        )
        compatibility = evaluate_planning_input_compatibility(
            workforce,
            fleet,
            expected_scope,
        )
        status = self._status(workforce, fleet, compatibility)
        producer_errors = tuple(
            error
            for error in (workforce_error, fleet_error)
            if error is not None
        )
        diagnostics = build_planning_input_diagnostics(
            compatibility,
            workforce,
            fleet,
            producer_errors,
        )
        envelope = None
        if status is PlanningInputRuntimeStatus.READY:
            envelope = compose_planning_input_envelope(
                workforce,
                fleet,
                created_at=composed_at,
            )
        report = PlanningInputCompositionReport(
            workforce=workforce,
            fleet=fleet,
            status=status,
            compatibility=compatibility,
            diagnostics=diagnostics,
            timestamp=composed_at,
            legacy_flow_active=True,
        )
        return PlanningInputCompositionResult(
            status=status,
            envelope=envelope,
            report=report,
        )
