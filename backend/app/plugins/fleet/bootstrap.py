import os

from fastapi import FastAPI

from app.plugins.fleet.infrastructure.repository import init_schema
from app.plugins.fleet.interfaces.router import router


def fleet_plugin_enabled() -> bool:
    value = os.getenv("FLEET_PLUGIN_ENABLED", "true")
    return value.strip().casefold() not in {"0", "false", "no", "off"}


def initialize_fleet_plugin() -> None:
    if fleet_plugin_enabled():
        init_schema()


def register_fleet_plugin(app: FastAPI) -> None:
    if fleet_plugin_enabled():
        app.include_router(router)
