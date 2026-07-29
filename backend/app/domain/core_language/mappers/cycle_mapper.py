from app.domain.core_language.models import TimeWindow


class CycleMapper:
    @staticmethod
    def to_core(cycle: str | None) -> TimeWindow | None:
        if cycle is None or cycle == "":
            return None
        return TimeWindow(external_identifier=cycle)

    @staticmethod
    def to_legacy(window: TimeWindow | None) -> str | None:
        return window.external_identifier if window else None
