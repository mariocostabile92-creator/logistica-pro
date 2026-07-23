from collections import Counter

from app.domain.core_language import ResourceKind
from app.domain.execution_attempt import ExecutionAttemptStatus
from app.domain.execution_intent import (
    ExecutionIntentStatus,
    ExecutionPublicationStatus,
)
from app.domain.planning_runtime.formatter import PlanningRuntimeOutputFormatter
from app.domain.planning_runtime.models import (
    PlanningRuntimeDiagnosticSeverity,
    PlanningRuntimeOutput,
    PlanningRuntimeOutputDiagnostic,
    PlanningRuntimeOutputDiagnostics,
    PlanningRuntimeProductionContext,
)
from app.domain.runtime_authority import AuthorityResolutionState


class PlanningRuntimeOutputValidator:
    def __init__(
        self,
        formatter: PlanningRuntimeOutputFormatter | None = None,
    ) -> None:
        self._formatter = formatter or PlanningRuntimeOutputFormatter()

    @staticmethod
    def _error(
        code: str,
        message: str,
        field: str | None = None,
    ) -> PlanningRuntimeOutputDiagnostic:
        return PlanningRuntimeOutputDiagnostic(
            code=code,
            severity=PlanningRuntimeDiagnosticSeverity.ERROR,
            message=message,
            field=field,
        )

    @staticmethod
    def _duplicates(values) -> tuple[str, ...]:
        counts = Counter(values)
        return tuple(sorted(value for value, count in counts.items() if count > 1))

    def validate_context(
        self,
        context: PlanningRuntimeProductionContext,
    ) -> PlanningRuntimeOutputDiagnostics:
        source = context.source
        authority = context.authority
        intent = context.intent
        attempt = context.attempt
        issues: list[PlanningRuntimeOutputDiagnostic] = []

        if (
            authority.state is not AuthorityResolutionState.WRITE_ALLOWED
            or authority.decision is None
        ):
            issues.append(self._error("AUTHORITY_INVALID", "Authority non valida."))
        if intent.status is not ExecutionIntentStatus.READY:
            issues.append(
                self._error(
                    "EXECUTION_INTENT_NOT_READY",
                    "Execution Intent non READY.",
                )
            )
        if attempt is None:
            issues.append(
                self._error(
                    "EXECUTION_ATTEMPT_MISSING",
                    "Execution Attempt assente.",
                )
            )
        elif attempt.status not in {
            ExecutionAttemptStatus.PENDING,
            ExecutionAttemptStatus.LOCK_ACQUIRED,
            ExecutionAttemptStatus.READY_TO_EXECUTE,
        }:
            issues.append(
                self._error(
                    "EXECUTION_ATTEMPT_INVALID",
                    "Execution Attempt non valido.",
                )
            )

        publication = source.publication
        if publication.status is not ExecutionPublicationStatus.PUBLISHED:
            issues.append(
                self._error("PUBLICATION_INVALID", "Publication non valida.")
            )
        publication_identity = (
            publication.organization_id,
            publication.operational_unit_id,
            publication.planning_date,
        )
        source_identity = source.scope.identity[:3]
        if publication_identity != source_identity:
            issues.append(
                self._error(
                    "PUBLICATION_SCOPE_MISMATCH",
                    "Publication e Runtime scope non coerenti.",
                    "scope",
                )
            )
        if (
            intent.scope.operational_identity != source.scope.identity
            or intent.scope.publication_id != publication.publication_id
            or intent.scope.publication_version != publication.publication_version
        ):
            issues.append(
                self._error(
                    "EXECUTION_INTENT_SCOPE_MISMATCH",
                    "Execution Intent e Runtime input non coerenti.",
                    "scope",
                )
            )
        if attempt is not None and (
            attempt.scope.execution_intent_id != intent.intent_id
            or attempt.publication_id != publication.publication_id
            or attempt.publication_version != publication.publication_version
        ):
            issues.append(
                self._error(
                    "EXECUTION_ATTEMPT_SCOPE_MISMATCH",
                    "Execution Attempt e Runtime input non coerenti.",
                    "attempt",
                )
            )
        if authority.decision is not None and attempt is not None and (
            authority.decision.decision_id != intent.authority_decision_id
            or authority.decision.decision_id != attempt.authority_decision_id
            or authority.decision.fencing_token != intent.fencing_token
            or authority.decision.fencing_token != attempt.fencing_token
        ):
            issues.append(
                self._error(
                    "FENCING_TOKEN_INVALID",
                    "Fencing obsoleto o non coerente.",
                    "fencing_token",
                )
            )

        resource_ids = tuple(
            item.external_identifier for item in source.resources
        )
        asset_ids = tuple(item.external_identifier for item in source.fleet)
        known_resources = set(resource_ids)
        known_assets = set(asset_ids)
        for duplicate in self._duplicates(resource_ids):
            issues.append(
                self._error(
                    "DUPLICATE_RESOURCE",
                    f"Resource duplicata: {duplicate}.",
                    "resources",
                )
            )
        for duplicate in self._duplicates(asset_ids):
            issues.append(
                self._error(
                    "DUPLICATE_ASSET",
                    f"Asset duplicato: {duplicate}.",
                    "fleet",
                )
            )
        task_ids = tuple(item.task_identifier for item in source.assignments)
        for duplicate in self._duplicates(task_ids):
            issues.append(
                self._error(
                    "DUPLICATE_ASSIGNMENT",
                    f"Assignment duplicato per Task: {duplicate}.",
                    "assignments",
                )
            )
        for assignment in source.assignments:
            if (
                assignment.resource_identifier is not None
                and assignment.resource_identifier not in known_resources
            ):
                issues.append(
                    self._error(
                        "UNKNOWN_ASSIGNMENT_RESOURCE",
                        "Assignment riferisce una Resource sconosciuta.",
                        "assignments",
                    )
                )
            if (
                assignment.asset_identifier is not None
                and assignment.asset_identifier not in known_assets
            ):
                issues.append(
                    self._error(
                        "UNKNOWN_ASSIGNMENT_ASSET",
                        "Assignment riferisce un Asset sconosciuto.",
                        "assignments",
                    )
                )
        for capability in source.capabilities:
            known = (
                known_resources
                if capability.resource_kind is ResourceKind.HUMAN_RESOURCE
                else known_assets
            )
            if capability.resource_identifier not in known:
                issues.append(
                    self._error(
                        "UNKNOWN_CAPABILITY_RESOURCE",
                        "Capability riferisce una Resource sconosciuta.",
                        "capabilities",
                    )
                )
        availability_keys = tuple(
            (item.resource_kind.value, item.resource_identifier)
            for item in source.availability
        )
        for duplicate in self._duplicates(availability_keys):
            issues.append(
                self._error(
                    "DUPLICATE_AVAILABILITY",
                    f"Availability duplicata: {duplicate}.",
                    "availability",
                )
            )
        for availability in source.availability:
            known = (
                known_resources
                if availability.resource_kind is ResourceKind.HUMAN_RESOURCE
                else known_assets
            )
            if availability.resource_identifier not in known:
                issues.append(
                    self._error(
                        "UNKNOWN_AVAILABILITY_RESOURCE",
                        "Availability riferisce una Resource sconosciuta.",
                        "availability",
                    )
                )

        if not issues:
            issues.append(
                PlanningRuntimeOutputDiagnostic(
                    code="RUNTIME_OUTPUT_INPUT_VALID",
                    severity=PlanningRuntimeDiagnosticSeverity.INFO,
                    message="Runtime Producer input valido.",
                )
            )
        return PlanningRuntimeOutputDiagnostics(
            valid=not any(
                item.severity is PlanningRuntimeDiagnosticSeverity.ERROR
                for item in issues
            ),
            items=tuple(issues),
            generated_at=source.evaluation_at,
        )

    def validate_output(
        self,
        output: PlanningRuntimeOutput,
    ) -> PlanningRuntimeOutputDiagnostics:
        issues: list[PlanningRuntimeOutputDiagnostic] = []
        expected_fingerprint = self._formatter.fingerprint_output(output)
        if output.fingerprint != expected_fingerprint:
            issues.append(
                self._error(
                    "OUTPUT_FINGERPRINT_MISMATCH",
                    "Runtime Output fingerprint non coerente.",
                    "fingerprint",
                )
            )
        order_checks = (
            (
                "resources",
                tuple(item.external_identifier for item in output.resources),
            ),
            (
                "fleet",
                tuple(item.external_identifier for item in output.fleet),
            ),
            (
                "assignments",
                tuple(
                    (
                        item.task_identifier,
                        item.resource_identifier or "",
                        item.asset_identifier or "",
                        item.state,
                    )
                    for item in output.assignments
                ),
            ),
            (
                "capabilities",
                tuple(
                    (
                        item.resource_kind.value,
                        item.resource_identifier,
                        item.capability,
                    )
                    for item in output.capabilities
                ),
            ),
            (
                "availability",
                tuple(
                    (
                        item.resource_kind.value,
                        item.resource_identifier,
                        str(item.available),
                        item.observed_state or "",
                    )
                    for item in output.availability
                ),
            ),
        )
        for field, values in order_checks:
            if values != tuple(sorted(values)):
                issues.append(
                    self._error(
                        "NON_DETERMINISTIC_ORDER",
                        f"Ordine non deterministico: {field}.",
                        field,
                    )
                )
        if not issues:
            issues.append(
                PlanningRuntimeOutputDiagnostic(
                    code="RUNTIME_OUTPUT_VALID",
                    severity=PlanningRuntimeDiagnosticSeverity.INFO,
                    message="Runtime Output completo e deterministico.",
                )
            )
        return PlanningRuntimeOutputDiagnostics(
            valid=not any(
                item.severity is PlanningRuntimeDiagnosticSeverity.ERROR
                for item in issues
            ),
            items=tuple(issues),
            generated_at=output.metadata.generated_at,
        )
