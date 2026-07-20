from dataclasses import dataclass

from app.briefing.models import AttentionLevel, BriefingSeverity


SEVERITY_BASE_SCORE = {
    BriefingSeverity.BLOCKER: 600,
    BriefingSeverity.CRITICAL: 500,
    BriefingSeverity.HIGH: 400,
    BriefingSeverity.MEDIUM: 300,
    BriefingSeverity.LOW: 200,
    BriefingSeverity.INFORMATION: 100,
}


@dataclass(frozen=True)
class AttentionInputs:
    planning_status: str
    uncovered_tasks: int
    readiness_level: str | None
    capacity_margin: int | None
    reserve_threshold: int | None
    severities: tuple[BriefingSeverity, ...]


def priority_score(
    severity: BriefingSeverity,
    urgency: int,
    operational_impact: int,
) -> int:
    return (
        SEVERITY_BASE_SCORE[severity]
        + urgency * 10
        + operational_impact
    )


def ranking_explanation(
    severity: BriefingSeverity,
    urgency: int,
    operational_impact: int,
) -> str:
    score = priority_score(severity, urgency, operational_impact)
    return (
        f"Severità {severity.value}, urgenza {urgency}/4 e impatto "
        f"operativo {operational_impact}/4 determinano il punteggio "
        f"{score}."
    )


def attention_level(
    inputs: AttentionInputs,
) -> tuple[AttentionLevel, str]:
    critical_severities = {
        BriefingSeverity.BLOCKER,
        BriefingSeverity.CRITICAL,
    }
    critical_reasons: list[str] = []
    if inputs.uncovered_tasks > 0:
        critical_reasons.append(
            f"{inputs.uncovered_tasks} Task non coperti"
        )
    if (
        inputs.planning_status == "critical"
        and not critical_reasons
    ):
        critical_reasons.append("Planning in stato critical")
    if inputs.readiness_level == "red":
        critical_reasons.append("Readiness red")
    if (
        inputs.capacity_margin is not None
        and inputs.capacity_margin < 0
        and inputs.uncovered_tasks == 0
    ):
        critical_reasons.append(
            f"margine Capacity {inputs.capacity_margin}"
        )
    if (
        critical_severities.intersection(inputs.severities)
        and not critical_reasons
    ):
        critical_reasons.append("issue blocker o critical")
    if critical_reasons:
        return (
            AttentionLevel.CRITICAL,
            "Livello critical: "
            + "; ".join(critical_reasons)
            + ". È richiesta una decisione umana.",
        )

    reduced_reserve = (
        inputs.capacity_margin is not None
        and inputs.reserve_threshold is not None
        and inputs.capacity_margin < inputs.reserve_threshold
    )
    attention_severities = {
        BriefingSeverity.HIGH,
        BriefingSeverity.MEDIUM,
    }
    attention_reasons: list[str] = []
    if inputs.readiness_level == "yellow":
        attention_reasons.append("Readiness yellow")
    if reduced_reserve:
        attention_reasons.append(
            f"margine {inputs.capacity_margin} sotto la soglia "
            f"{inputs.reserve_threshold}"
        )
    relevant_issues = sum(
        severity in attention_severities
        for severity in inputs.severities
    )
    if relevant_issues:
        attention_reasons.append(
            f"{relevant_issues} issue high o medium"
        )
    if attention_reasons:
        return (
            AttentionLevel.ATTENTION,
            "Livello attention: "
            + "; ".join(attention_reasons)
            + ". È richiesta una verifica prima dell'avvio.",
        )

    return (
        AttentionLevel.STABLE,
        "Non risultano condizioni bloccanti e il margine operativo "
        "rispetta la soglia configurata.",
    )
