from app.domain.core_language.models import AssetReference


class VehicleMapper:
    @staticmethod
    def to_core(vehicle: str | None) -> AssetReference | None:
        if vehicle is None or vehicle == "":
            return None
        return AssetReference(external_identifier=vehicle)

    @staticmethod
    def to_legacy(asset: AssetReference | None) -> str | None:
        return asset.external_identifier if asset else None
