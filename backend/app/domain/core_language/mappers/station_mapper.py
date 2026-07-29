from app.domain.core_language.models import OperationalUnit


class StationMapper:
    @staticmethod
    def to_core(station: str | None) -> OperationalUnit | None:
        if station is None or station == "":
            return None
        return OperationalUnit(external_identifier=station)

    @staticmethod
    def to_legacy(unit: OperationalUnit | None) -> str | None:
        return unit.external_identifier if unit else None
