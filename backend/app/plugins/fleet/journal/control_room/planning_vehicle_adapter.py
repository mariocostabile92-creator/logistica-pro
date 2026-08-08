from app.utils.text_normalizer import normalize_plate


ACTIVE_ASSIGNMENT_STATUSES = {
    "proposed",
    "confirmed",
    "warning",
    "manually_changed",
}


def index_fleet_assets_by_plate(
    assets: list[dict],
) -> dict[str, dict]:
    return {
        normalize_plate(str(asset.get("plate") or "")): asset
        for asset in assets
        if asset.get("plate")
    }


def fleet_asset_for_assignment(
    assignment: dict,
    assets_by_plate: dict[str, dict],
) -> dict | None:
    return assets_by_plate.get(
        normalize_plate(str(assignment.get("plate") or ""))
    )


def assignment_is_active(assignment: dict) -> bool:
    return assignment.get("assignment_status") in ACTIVE_ASSIGNMENT_STATUSES
