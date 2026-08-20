from decimal import Decimal

from app.domain.core_language import TimeWindow
from app.domain.workforce_auto_planning import (
    OperationalBufferPolicy,
    PlanningPriorityOrPreference,
    PlanningRuleDescriptor,
    ShiftCatalogueEntry,
    WorkloadCapabilityMapping,
)


class AmazonOperationalBufferPolicyProvider:
    def __init__(self, target_multiplier: Decimal = Decimal("1.10")) -> None:
        self._buffer_policy = OperationalBufferPolicy(
            identifier="amazon-operational-buffer",
            target_multiplier=target_multiplier,
        )

    def operational_buffer_policy(self) -> OperationalBufferPolicy:
        return self._buffer_policy

    def shift_catalogue(self) -> tuple[ShiftCatalogueEntry, ...]:
        return ()

    def time_windows(self) -> tuple[TimeWindow, ...]:
        return ()

    def workload_capability_mappings(
        self,
    ) -> tuple[WorkloadCapabilityMapping, ...]:
        return ()

    def priorities_and_preferences(
        self,
    ) -> tuple[PlanningPriorityOrPreference, ...]:
        return ()

    def additional_rules(self) -> tuple[PlanningRuleDescriptor, ...]:
        return ()
