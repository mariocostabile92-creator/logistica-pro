from app.adapters.amazon.operational_buffer_policy import (
    AmazonOperationalBufferPolicyProvider,
)
from app.domain.core_language import TimeWindow
from app.domain.workforce_auto_planning import (
    ShiftCatalogueEntry,
    WorkloadCapabilityMapping,
)


_NEXT_DAY_WINDOW = "amazon-next-day"
_SAME_DAY_A_WINDOW = "amazon-same-day-a"
_SAME_DAY_B_C_WINDOW = "amazon-same-day-b-c"

_NEXT_DAY_CAPABILITY = "amazon-workload-next-day"
_SAME_DAY_A_CAPABILITY = "amazon-workload-same-day-a"
_SAME_DAY_B_C_CAPABILITY = "amazon-workload-same-day-b-c"


class AmazonShiftTimeWindowPolicyProvider(
    AmazonOperationalBufferPolicyProvider
):
    def shift_catalogue(self) -> tuple[ShiftCatalogueEntry, ...]:
        return (
            *(
                ShiftCatalogueEntry(
                    identifier=code,
                    label=code,
                    time_window_identifier=_NEXT_DAY_WINDOW,
                    required_capabilities=(_NEXT_DAY_CAPABILITY,),
                )
                for code in ("C1", "L1", "L2", "L3", "VMC1")
            ),
            ShiftCatalogueEntry(
                identifier="SA",
                label="SA",
                time_window_identifier=_SAME_DAY_A_WINDOW,
                required_capabilities=(_SAME_DAY_A_CAPABILITY,),
            ),
            ShiftCatalogueEntry(
                identifier="SB",
                label="SB",
                time_window_identifier=_SAME_DAY_B_C_WINDOW,
                required_capabilities=(_SAME_DAY_B_C_CAPABILITY,),
            ),
        )

    def time_windows(self) -> tuple[TimeWindow, ...]:
        return tuple(
            TimeWindow(external_identifier=identifier)
            for identifier in (
                _NEXT_DAY_WINDOW,
                _SAME_DAY_A_WINDOW,
                _SAME_DAY_B_C_WINDOW,
            )
        )

    def workload_capability_mappings(
        self,
    ) -> tuple[WorkloadCapabilityMapping, ...]:
        return (
            WorkloadCapabilityMapping(
                workload_identifier="NEXT_DAY",
                required_capabilities=(_NEXT_DAY_CAPABILITY,),
            ),
            WorkloadCapabilityMapping(
                workload_identifier="SAME_DAY:A",
                required_capabilities=(_SAME_DAY_A_CAPABILITY,),
            ),
            WorkloadCapabilityMapping(
                workload_identifier="SAME_DAY:B_C",
                required_capabilities=(_SAME_DAY_B_C_CAPABILITY,),
            ),
        )
