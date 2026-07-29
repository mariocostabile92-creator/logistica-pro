from app.adapters.amazon import AMAZON_ADAPTER


# Compatibility export. The canonical source is catalog.v1.json.
AMAZON_EVENT_ALIASES = {
    alias: mapping.compatibility_event
    for mapping in AMAZON_ADAPTER.event_mappings()
    for alias in mapping.aliases
    if mapping.compatibility_event
}
