from collections.abc import Callable

from pydantic import ValidationError

from app.core.configuration import repository
from app.core.configuration.models import (
    ConfigurationRevision,
    ConfigurationScope,
)
from app.core.configuration.repository import (
    ConfigurationStorageUnavailableError,
    StoredConfigurationInvalidError,
)
from app.domain.workforce_auto_planning import (
    PlanningOperationalUnitBinding,
)


PLANNING_BINDING_ADAPTER_ID = "workforce-auto-planning-bindings"
PLANNING_BINDING_SECTION_KEY = "planning_operational_unit_bindings"
PLANNING_BINDING_VALUE_KEY = "bindings"


class PlanningOperationalUnitBindingResolutionError(RuntimeError):
    """Base error for fail-closed planning unit binding resolution."""


class PlanningOperationalUnitBindingNotFoundError(
    PlanningOperationalUnitBindingResolutionError
):
    pass


class PlanningOperationalUnitBindingAmbiguousError(
    PlanningOperationalUnitBindingResolutionError
):
    pass


class PlanningOperationalUnitBindingMalformedError(
    PlanningOperationalUnitBindingResolutionError
):
    pass


class PlanningOperationalUnitBindingStorageError(
    PlanningOperationalUnitBindingResolutionError
):
    pass


RevisionLoader = Callable[[ConfigurationScope], ConfigurationRevision | None]


def _required_text(value: str, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} cannot be empty")
    return value.strip()


class ConfigurationPlanningOperationalUnitBindingProvider:
    """Resolve typed bindings from one exact Configuration Engine scope."""

    def __init__(
        self,
        revision_loader: RevisionLoader | None = None,
    ) -> None:
        self._revision_loader = (
            revision_loader or repository.get_latest_revision
        )

    def resolve_binding(
        self,
        *,
        organization_id: str,
        demand_source_context: str,
    ) -> PlanningOperationalUnitBinding:
        organization = _required_text(organization_id, "organization_id")
        source_context = _required_text(
            demand_source_context,
            "demand_source_context",
        )
        scope = ConfigurationScope(
            organization_id=organization,
            adapter_id=PLANNING_BINDING_ADAPTER_ID,
        )
        revision = self._load_revision(scope)
        if revision is None:
            raise PlanningOperationalUnitBindingNotFoundError(
                "No active planning operational unit binding was found."
            )
        self._validate_exact_scope(revision, scope)
        bindings = self._parse_bindings(revision, organization)
        matches = [
            binding
            for binding in bindings
            if binding.active
            and binding.demand_source_context == source_context
        ]
        if not matches:
            raise PlanningOperationalUnitBindingNotFoundError(
                "No active planning operational unit binding was found."
            )
        if len(matches) > 1:
            raise PlanningOperationalUnitBindingAmbiguousError(
                "Multiple active planning operational unit bindings were found."
            )
        return matches[0]

    def _load_revision(
        self,
        scope: ConfigurationScope,
    ) -> ConfigurationRevision | None:
        try:
            return self._revision_loader(scope)
        except StoredConfigurationInvalidError as exc:
            raise PlanningOperationalUnitBindingMalformedError(
                "Planning operational unit binding configuration is malformed."
            ) from exc
        except ConfigurationStorageUnavailableError as exc:
            raise PlanningOperationalUnitBindingStorageError(
                "Planning operational unit binding storage is unavailable."
            ) from exc

    @staticmethod
    def _validate_exact_scope(
        revision: ConfigurationRevision,
        expected_scope: ConfigurationScope,
    ) -> None:
        if revision.scope != expected_scope:
            raise PlanningOperationalUnitBindingMalformedError(
                "Planning operational unit binding scope does not match the request."
            )

    @staticmethod
    def _parse_bindings(
        revision: ConfigurationRevision,
        organization_id: str,
    ) -> tuple[PlanningOperationalUnitBinding, ...]:
        sections = [
            section
            for section in revision.sections
            if section.key == PLANNING_BINDING_SECTION_KEY
        ]
        if not sections:
            return ()
        if len(sections) != 1:
            raise PlanningOperationalUnitBindingMalformedError(
                "Planning operational unit binding section is ambiguous."
            )
        values = [
            value
            for value in sections[0].values
            if value.key == PLANNING_BINDING_VALUE_KEY
        ]
        if not values:
            return ()
        raw_bindings = values[0].value
        if not isinstance(raw_bindings, list):
            raise PlanningOperationalUnitBindingMalformedError(
                "Planning operational unit bindings must be a list."
            )
        parsed: list[PlanningOperationalUnitBinding] = []
        try:
            for raw_binding in raw_bindings:
                if not isinstance(raw_binding, dict):
                    raise TypeError("Binding entry must be an object.")
                payload = dict(raw_binding)
                payload["organization_id"] = organization_id
                payload["binding_version"] = revision.version.number
                parsed.append(
                    PlanningOperationalUnitBinding.model_validate(payload)
                )
        except (TypeError, ValidationError, ValueError) as exc:
            raise PlanningOperationalUnitBindingMalformedError(
                "Planning operational unit binding configuration is malformed."
            ) from exc
        return tuple(parsed)
