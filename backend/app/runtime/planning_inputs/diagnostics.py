from app.domain.planning_inputs import PlanningInputSnapshot, PlanningInputStatus
from app.runtime.planning_inputs.models import (
    PlanningInputCompatibility,
    PlanningInputDiagnostics,
)


def _unique(values: list[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(values))


def build_planning_input_diagnostics(
    compatibility: PlanningInputCompatibility,
    workforce: PlanningInputSnapshot | None,
    fleet: PlanningInputSnapshot | None,
    producer_errors: tuple[str, ...] = (),
) -> PlanningInputDiagnostics:
    warnings: list[str] = []
    errors = list(producer_errors)
    reasons: list[str] = []

    for check in compatibility.checks:
        if check.compatible is True:
            continue
        reasons.append(check.message)
        if check.compatible is False and check.code != "VALIDATION":
            errors.append(check.message)

    for label, snapshot in (("Workforce", workforce), ("Fleet", fleet)):
        if snapshot is None:
            continue
        status = snapshot.validation.status
        if status in {PlanningInputStatus.PARTIAL, PlanningInputStatus.STALE}:
            warnings.append(f"{label} {status.value}.")
        elif status in {PlanningInputStatus.MISSING, PlanningInputStatus.INVALID}:
            errors.append(f"{label} {status.value}.")
        for issue in snapshot.validation.issues:
            target = errors if issue.blocking else warnings
            target.append(f"{label}: {issue.message}")
            reasons.append(f"{label}: {issue.message}")

    return PlanningInputDiagnostics(
        warnings=_unique(warnings),
        errors=_unique(errors),
        reasons=_unique(reasons),
    )
