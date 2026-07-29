from app.domain.core_language.models import HumanResource


class DriverMapper:
    @staticmethod
    def to_core(
        driver: str | None,
        display_name: str | None = None,
    ) -> HumanResource | None:
        if driver is None or driver == "":
            return None
        return HumanResource(
            external_identifier=driver,
            display_name=display_name,
        )

    @staticmethod
    def to_legacy(resource: HumanResource | None) -> str | None:
        return resource.external_identifier if resource else None
