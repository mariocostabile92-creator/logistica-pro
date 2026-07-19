from app.adapters.amazon import AMAZON_ADAPTER


def amazon_planning_aliases(
    organization_id: str = "default",
) -> dict[str, list[str]]:
    return AMAZON_ADAPTER.aliases_for(
        "planning",
        organization_id=organization_id,
    )
