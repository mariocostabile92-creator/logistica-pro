from app.core.configuration.models import ConfigurationScope
from app.core.configuration.service import get_current_configuration


def fleet_registry_configuration() -> dict[str, object]:
    configuration = get_current_configuration(
        ConfigurationScope(organization_id="default")
    )
    for section in configuration.sections:
        if section.key == "fleet_registry":
            return {item.key: item.value for item in section.values}
    return {}
