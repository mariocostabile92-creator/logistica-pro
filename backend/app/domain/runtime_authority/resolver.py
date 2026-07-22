from datetime import datetime

from app.domain.runtime_authority.models import (
    AuthorityConflict,
    AuthorityDecision,
    AuthorityDecisionMode,
    AuthorityResolutionResult,
    AuthorityResolutionState,
    AuthorityScope,
    AuthorityStatus,
)
from app.domain.runtime_authority.validator import AuthorityValidator


_WRITE_MODES = {
    AuthorityDecisionMode.LEGACY,
    AuthorityDecisionMode.RUNTIME,
}


class AuthorityResolver:
    def __init__(self, validator: AuthorityValidator) -> None:
        self._validator = validator

    def resolve(
        self,
        *,
        scope: AuthorityScope,
        decisions: tuple[AuthorityDecision, ...],
        assessed_at: datetime,
    ) -> AuthorityResolutionResult:
        if assessed_at.utcoffset() is None:
            raise ValueError("assessed_at must be timezone-aware.")

        matching = tuple(
            decision
            for decision in decisions
            if self._validator.validate_scope(decision, scope) is None
        )
        active = tuple(
            decision
            for decision in matching
            if self._validator.effective_status(
                decision,
                assessed_at=assessed_at,
            )
            is AuthorityStatus.ACTIVE
        )

        if len(active) > 1:
            ordered = tuple(
                sorted(
                    active,
                    key=lambda item: (
                        item.priority,
                        int(item.version),
                        item.fencing_token,
                    ),
                    reverse=True,
                )[:20]
            )
            conflict = AuthorityConflict(
                code="AUTHORITY_OVERLAP",
                message="Authority sovrapposta. Nessun writer autorizzato.",
                decision_ids=tuple(item.decision_id for item in ordered),
                priorities=tuple(item.priority for item in ordered),
                versions=tuple(int(item.version) for item in ordered),
                fencing_tokens=tuple(item.fencing_token for item in ordered),
            )
            return self._no_write(
                scope=scope,
                assessed_at=assessed_at,
                code="AUTHORITY_CONFLICT",
                reason="Authority conflittuale. Scrittura bloccata.",
                conflicts=(conflict,),
            )

        if not active:
            return self._no_active_resolution(
                scope=scope,
                decisions=matching,
                assessed_at=assessed_at,
            )

        decision = active[0]
        if decision.mode not in _WRITE_MODES:
            return self._no_write(
                scope=scope,
                assessed_at=assessed_at,
                code="AUTHORITY_MODE_NO_WRITE",
                reason=(
                    f"Authority in modalita {decision.mode.value}: "
                    "scrittura non autorizzata."
                ),
                decision=decision,
            )
        return AuthorityResolutionResult(
            state=AuthorityResolutionState.WRITE_ALLOWED,
            scope=scope,
            decision=decision,
            reason_code="AUTHORITY_WRITE_ALLOWED",
            reason=(
                f"Authority valida. Writer autorizzato: "
                f"{decision.mode.value}."
            ),
            assessed_at=assessed_at,
        )

    def _no_active_resolution(
        self,
        *,
        scope: AuthorityScope,
        decisions: tuple[AuthorityDecision, ...],
        assessed_at: datetime,
    ) -> AuthorityResolutionResult:
        if not decisions:
            return self._no_write(
                scope=scope,
                assessed_at=assessed_at,
                code="AUTHORITY_SCOPE_NOT_FOUND",
                reason="Scope non trovato. Nessuna Authority disponibile.",
            )

        ranked = tuple(
            sorted(
                decisions,
                key=lambda item: (
                    int(item.version),
                    item.fencing_token,
                ),
                reverse=True,
            )
        )
        decision = ranked[0]
        status = self._validator.effective_status(
            decision,
            assessed_at=assessed_at,
        )
        effective = decision.model_copy(update={"status": status})
        messages = {
            AuthorityStatus.EXPIRED: (
                "AUTHORITY_EXPIRED",
                "Authority scaduta. Scrittura bloccata.",
            ),
            AuthorityStatus.SUPERSEDED: (
                "AUTHORITY_SUPERSEDED",
                "Authority superata. Scrittura bloccata.",
            ),
            AuthorityStatus.REVOKED: (
                "AUTHORITY_REVOKED",
                "Authority revocata. Scrittura bloccata.",
            ),
            AuthorityStatus.INVALID: (
                "AUTHORITY_INVALID",
                "Authority non valida o non ancora attiva.",
            ),
        }
        code, reason = messages[status]
        return self._no_write(
            scope=scope,
            assessed_at=assessed_at,
            code=code,
            reason=reason,
            decision=effective,
        )

    @staticmethod
    def _no_write(
        *,
        scope: AuthorityScope,
        assessed_at: datetime,
        code: str,
        reason: str,
        decision: AuthorityDecision | None = None,
        conflicts: tuple[AuthorityConflict, ...] = (),
    ) -> AuthorityResolutionResult:
        return AuthorityResolutionResult(
            state=AuthorityResolutionState.NO_WRITE,
            scope=scope,
            decision=decision,
            reason_code=code,
            reason=reason,
            conflicts=conflicts,
            assessed_at=assessed_at,
        )
