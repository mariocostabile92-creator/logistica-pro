from app.core.configuration.models import ConfigurationScope
from app.core.configuration.service import get_current_configuration


def _values(section_key: str) -> dict[str, object]:
    configuration = get_current_configuration(
        ConfigurationScope(organization_id="default")
    )
    for section in configuration.sections:
        if section.key == section_key:
            return {item.key: item.value for item in section.values}
    return {}


def workforce_status_configuration() -> dict[str, object]:
    return _values("workforce_statuses")


def workforce_shift_configuration() -> dict[str, object]:
    return _values("workforce_shift_codes")
