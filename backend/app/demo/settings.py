import os

from app.core.config import SETTINGS


def demo_workspace_enabled(
    environ: dict[str, str] | None = None,
) -> bool:
    values = os.environ if environ is None else environ
    configured = values.get("DEMO_WORKSPACE_ENABLED")
    if configured is None:
        return not SETTINGS.production
    return configured.strip().casefold() in {"1", "true", "yes", "on"}

