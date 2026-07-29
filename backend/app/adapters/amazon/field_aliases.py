from app.adapters.amazon import AMAZON_ADAPTER


# Compatibility export. The canonical source is catalog.v1.json.
AMAZON_PLANNING_FIELD_ALIASES = AMAZON_ADAPTER.base_aliases_for(
    "planning"
)
