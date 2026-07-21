import os

from fastapi import FastAPI

from app.plugins.workforce.infrastructure.schema import init_schema
from app.plugins.workforce.interfaces.router import router


def workforce_plugin_enabled() -> bool:
    value = os.getenv("WORKFORCE_PLUGIN_ENABLED", "false")
    return value.strip().casefold() in {"1", "true", "yes", "on"}


def initialize_workforce_plugin() -> None:
    init_schema()


def register_workforce_plugin(app: FastAPI) -> None:
    if workforce_plugin_enabled():
        app.include_router(router)
