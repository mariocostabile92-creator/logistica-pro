import hashlib
from collections import Counter
from collections.abc import Callable
from datetime import datetime
from time import perf_counter

from app.domain.runtime_shadow.formatter import PlanningComparatorFormatter
from app.domain.runtime_shadow.models import (
    PlanningComparatorResult,
    PlanningMismatch,
    PlanningMismatchCategory,
    PlanningMismatchDistribution,
    PlanningMismatchSeverity,
    PlanningParityReport,
    RuntimeShadowSnapshot,
)


class PlanningComparator:
    def __init__(
        self,
        *,
        clock: Callable[[], datetime],
        timer: Callable[[], float] = perf_counter,
        formatter: PlanningComparatorFormatter | None = None,
    ) -> None:
        self._clock = clock
        self._timer = timer
        self._formatter = formatter or PlanningComparatorFormatter()

    def compare(
        self,
        *,
        legacy: RuntimeShadowSnapshot,
        runtime: RuntimeShadowSnapshot,
    ) -> PlanningComparatorResult:
        started = self._timer()
        compared_at = self._clock()
        mismatches: list[PlanningMismatch] = []
        missing_total = 0
        unexpected_total = 0

        scalar_specs = (
            (
                "Input fingerprint",
                legacy.input_fingerprint,
                runtime.input_fingerprint,
                PlanningMismatchCategory.VALIDATION,
                PlanningMismatchSeverity.CRITICAL,
                "Usa lo stesso PlanningInputEnvelope per entrambi i calcoli.",
            ),
            (
                "Configuration version",
                legacy.configuration_version,
                runtime.configuration_version,
                PlanningMismatchCategory.VALIDATION,
                PlanningMismatchSeverity.CRITICAL,
                "Allinea la configurazione risolta dei due calcoli.",
            ),
            (
                "Rules version",
                legacy.rules_version,
                runtime.rules_version,
                PlanningMismatchCategory.VALIDATION,
                PlanningMismatchSeverity.CRITICAL,
                "Allinea la versione delle regole.",
            ),
            (
                "Evaluation timestamp",
                legacy.evaluation_at,
                runtime.evaluation_at,
                PlanningMismatchCategory.VALIDATION,
                PlanningMismatchSeverity.CRITICAL,
                "Ripeti il confronto allo stesso istante di valutazione.",
            ),
            (
                "Organization",
                legacy.scope.organization_id,
                runtime.scope.organization_id,
                PlanningMismatchCategory.SCOPE,
                PlanningMismatchSeverity.CRITICAL,
                "Usa lo stesso organization scope.",
            ),
            (
                "Operational Unit",
                legacy.scope.operational_unit_id,
                runtime.scope.operational_unit_id,
                PlanningMismatchCategory.SCOPE,
                PlanningMismatchSeverity.CRITICAL,
                "Usa la stessa Operational Unit.",
            ),
            (
                "Planning Date",
                legacy.scope.planning_date,
                runtime.scope.planning_date,
                PlanningMismatchCategory.SCOPE,
                PlanningMismatchSeverity.CRITICAL,
                "Usa la stessa data operativa.",
            ),
            (
                "Timezone",
                legacy.scope.timezone,
                runtime.scope.timezone,
                PlanningMismatchCategory.SCOPE,
                PlanningMismatchSeverity.CRITICAL,
                "Usa la stessa timezone IANA.",
            ),
            (
                "Publication",
                legacy.publication.publication_id,
                runtime.publication.publication_id,
                PlanningMismatchCategory.SCOPE,
                PlanningMismatchSeverity.CRITICAL,
                "Confronta la stessa Publication.",
            ),
            (
                "Publication Version",
                legacy.publication.publication_version,
                runtime.publication.publication_version,
                PlanningMismatchCategory.VERSION,
                PlanningMismatchSeverity.HIGH,
                "Allinea la versione della Publication.",
            ),
            (
                "Planning Version",
                legacy.planning_version,
                runtime.planning_version,
                PlanningMismatchCategory.VERSION,
                PlanningMismatchSeverity.HIGH,
                "Allinea la versione del risultato Planning.",
            ),
            (
                "Fingerprint",
                legacy.fingerprint,
                runtime.fingerprint,
                PlanningMismatchCategory.FINGERPRINT,
                PlanningMismatchSeverity.CRITICAL,
                "Ricalcola e verifica entrambi i fingerprint.",
            ),
        )
        for title, legacy_value, runtime_value, category, severity, action in scalar_specs:
            if legacy_value != runtime_value:
                mismatches.append(
                    self._mismatch(
                        title=title,
                        category=category,
                        severity=severity,
                        legacy_value=legacy_value,
                        runtime_value=runtime_value,
                        legacy=legacy,
                        compared_at=compared_at,
                        suggested_action=action,
                    )
                )

        collection_specs = (
            (
                "Resources",
                legacy.resources,
                runtime.resources,
                PlanningMismatchCategory.RESOURCE,
                PlanningMismatchSeverity.HIGH,
                "Verifica risorse mancanti o inattese.",
            ),
            (
                "Fleet",
                legacy.fleet,
                runtime.fleet,
                PlanningMismatchCategory.FLEET,
                PlanningMismatchSeverity.HIGH,
                "Verifica gli Asset Fleet usati dal calcolo.",
            ),
            (
                "Assignments",
                legacy.assignments,
                runtime.assignments,
                PlanningMismatchCategory.ASSIGNMENT,
                PlanningMismatchSeverity.CRITICAL,
                "Rivedi le assegnazioni divergenti.",
            ),
            (
                "Capabilities",
                legacy.capabilities,
                runtime.capabilities,
                PlanningMismatchCategory.CAPABILITY,
                PlanningMismatchSeverity.MEDIUM,
                "Allinea capability e requisiti applicati.",
            ),
            (
                "Availability",
                legacy.availability,
                runtime.availability,
                PlanningMismatchCategory.RESOURCE,
                PlanningMismatchSeverity.HIGH,
                "Allinea lo snapshot Availability.",
            ),
            (
                "Validation",
                legacy.validation_errors,
                runtime.validation_errors,
                PlanningMismatchCategory.VALIDATION,
                PlanningMismatchSeverity.HIGH,
                "Risolvi le differenze di validazione.",
            ),
        )
        for title, legacy_values, runtime_values, category, severity, action in collection_specs:
            legacy_counts = Counter(legacy_values)
            runtime_counts = Counter(runtime_values)
            missing = tuple((legacy_counts - runtime_counts).elements())
            unexpected = tuple((runtime_counts - legacy_counts).elements())
            if missing or unexpected:
                missing_total += len(missing)
                unexpected_total += len(unexpected)
                mismatches.append(
                    self._mismatch(
                        title=title,
                        category=category,
                        severity=severity,
                        legacy_value=legacy_values,
                        runtime_value=runtime_values,
                        legacy=legacy,
                        compared_at=compared_at,
                        suggested_action=action,
                        missing=missing,
                        unexpected=unexpected,
                    )
                )

        total_comparisons = len(scalar_specs) + len(collection_specs)
        comparability_titles = {
            "Input fingerprint",
            "Configuration version",
            "Rules version",
            "Evaluation timestamp",
            "Organization",
            "Operational Unit",
            "Planning Date",
            "Timezone",
            "Publication",
            "Publication Version",
        }
        comparable = not any(
            mismatch.title in comparability_titles
            for mismatch in mismatches
        )
        parity = (
            round(
                (total_comparisons - len(mismatches))
                / total_comparisons
                * 100,
                2,
            )
            if comparable
            else 0.0
        )
        elapsed_ms = max(0.0, (self._timer() - started) * 1_000)
        counts = Counter(mismatch.category for mismatch in mismatches)
        report = PlanningParityReport(
            parity_percent=parity,
            mismatch_percent=round(100.0 - parity, 2),
            perfect_match=comparable and not mismatches,
            comparable=comparable,
            total_comparisons=total_comparisons,
            total_mismatches=len(mismatches),
            missing=missing_total,
            unexpected=unexpected_total,
            mismatch_distribution=tuple(
                PlanningMismatchDistribution(category=category, count=count)
                for category, count in sorted(
                    counts.items(),
                    key=lambda item: item[0].value,
                )
            ),
            comparison_time_ms=elapsed_ms,
            planning_version=runtime.planning_version,
            publication_version=runtime.publication.publication_version,
            operational_unit=runtime.scope.operational_unit_id,
            planning_date=runtime.scope.planning_date,
            parity_target_met=comparable and parity >= 99.5,
        )
        return PlanningComparatorResult(
            report=report,
            mismatches=tuple(mismatches),
            compared_at=compared_at,
        )

    def _mismatch(
        self,
        *,
        title: str,
        category: PlanningMismatchCategory,
        severity: PlanningMismatchSeverity,
        legacy_value: object,
        runtime_value: object,
        legacy: RuntimeShadowSnapshot,
        compared_at: datetime,
        suggested_action: str,
        missing: tuple[str, ...] | None = None,
        unexpected: tuple[str, ...] | None = None,
    ) -> PlanningMismatch:
        legacy_rendered = self._formatter.value(legacy_value)
        runtime_rendered = self._formatter.value(runtime_value)
        difference = self._formatter.difference(
            missing=missing or (),
            unexpected=unexpected or (),
            legacy_value=legacy_rendered,
            runtime_value=runtime_rendered,
        )
        mismatch_id = hashlib.sha256(
            (
                f"planning-mismatch:v1|{category.value}|{title}|"
                f"{legacy.scope.identity}|{legacy.publication.publication_id}|"
                f"{legacy_rendered}|{runtime_rendered}"
            ).encode("utf-8")
        ).hexdigest()[:32]
        return PlanningMismatch(
            id=f"mismatch-{mismatch_id}",
            category=category,
            severity=severity,
            title=title,
            description=f"Legacy e Runtime divergono su {title}.",
            legacy_value=legacy_rendered,
            runtime_value=runtime_rendered,
            difference=difference,
            scope=legacy.scope,
            publication=legacy.publication,
            timestamp=compared_at,
            suggested_action=suggested_action,
        )
