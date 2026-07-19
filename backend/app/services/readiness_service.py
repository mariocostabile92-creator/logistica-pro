from app.domain.conflict_types import ConflictSeverity
from app.domain.operations_engine import (
    OperationalCapacity,
    OperationalIssue,
    OperationalReadiness,
    OperationalRisk,
    OperationalStatus,
)


def calculate_readiness(
    capacity: OperationalCapacity,
    issues: list[OperationalIssue],
    reserve_threshold: int,
) -> OperationalReadiness:
    critical_count = sum(
        1 for issue in issues if issue.severity == ConflictSeverity.CRITICAL
    )
    warning_count = sum(
        1 for issue in issues if issue.severity == ConflictSeverity.WARNING
    )
    reasons: list[str] = []
    triggered_rules: list[str] = []

    if capacity.operational_margin < 0:
        shortage = abs(capacity.operational_margin)
        reasons.append(f"Mancano {shortage} mezzi operativi per coprire tutte le rotte.")
        triggered_rules.append("CAPACITY_SHORTAGE")

    if capacity.driver_margin < 0:
        shortage = abs(capacity.driver_margin)
        reasons.append(f"Mancano {shortage} driver riconosciuti per coprire tutte le rotte.")
        triggered_rules.append("DRIVER_SHORTAGE")

    if critical_count:
        reasons.append(f"Sono presenti {critical_count} problemi critici da risolvere.")
        triggered_rules.append("CRITICAL_ISSUES")

    has_blocking_condition = (
        capacity.operational_margin < 0
        or capacity.driver_margin < 0
        or critical_count > 0
    )
    if has_blocking_condition:
        return OperationalReadiness(
            status=OperationalStatus.RED,
            risk_level=OperationalRisk.HIGH,
            can_start_all_routes=False,
            operational_margin=capacity.operational_margin,
            reserve_threshold=reserve_threshold,
            critical_issues=critical_count,
            warning_issues=warning_count,
            reasons=reasons,
            triggered_rules=triggered_rules,
        )

    if capacity.operational_margin < reserve_threshold:
        reasons.append(
            f"Il margine operativo è {capacity.operational_margin}, sotto la soglia {reserve_threshold}."
        )
        triggered_rules.append("LOW_RESERVE_MARGIN")

    if warning_count:
        reasons.append(f"Sono presenti {warning_count} avvisi operativi da verificare.")
        triggered_rules.append("WARNING_ISSUES")

    if triggered_rules:
        return OperationalReadiness(
            status=OperationalStatus.YELLOW,
            risk_level=OperationalRisk.MEDIUM,
            can_start_all_routes=True,
            operational_margin=capacity.operational_margin,
            reserve_threshold=reserve_threshold,
            critical_issues=critical_count,
            warning_issues=warning_count,
            reasons=reasons,
            triggered_rules=triggered_rules,
        )

    return OperationalReadiness(
        status=OperationalStatus.GREEN,
        risk_level=OperationalRisk.LOW,
        can_start_all_routes=True,
        operational_margin=capacity.operational_margin,
        reserve_threshold=reserve_threshold,
        critical_issues=critical_count,
        warning_issues=warning_count,
        reasons=["Capacità, driver e margine di riserva rispettano le regole operative."],
        triggered_rules=["READY"],
    )
