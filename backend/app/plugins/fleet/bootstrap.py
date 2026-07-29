import os

from fastapi import FastAPI

from app.plugins.fleet.infrastructure.repository import init_schema
from app.plugins.fleet.infrastructure.sync_schema import init_sync_schema
from app.plugins.fleet.interfaces.router import router
from app.plugins.fleet.interfaces.sync_router import router as sync_router
from app.plugins.fleet.journal.infrastructure.repository import (
    init_schema as init_journal_schema,
)
from app.plugins.fleet.journal.interfaces.router import router as journal_router


def fleet_plugin_enabled() -> bool:
    value = os.getenv("FLEET_PLUGIN_ENABLED", "true")
    return value.strip().casefold() not in {"0", "false", "no", "off"}


def initialize_fleet_plugin() -> None:
    if fleet_plugin_enabled():
        init_schema()
        init_sync_schema()
        init_journal_schema()


def register_fleet_plugin(app: FastAPI) -> None:
    if fleet_plugin_enabled():
        app.include_router(router)
        app.include_router(sync_router)
        app.include_router(journal_router)
