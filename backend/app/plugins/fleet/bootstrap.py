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
from app.plugins.fleet.journal.control_room.router import router as control_room_router
from app.plugins.fleet.damage.infrastructure.repository import init_schema as init_damage_schema
from app.plugins.fleet.damage.interfaces.router import router as damage_router
from app.plugins.fleet.maintenance.infrastructure.repository import (
    init_schema as init_maintenance_schema,
)
from app.plugins.fleet.maintenance.interfaces.router import (
    router as maintenance_router,
)
from app.plugins.fleet.documents.infrastructure.repository import (
    init_schema as init_documents_schema,
)
from app.plugins.fleet.documents.interfaces.router import router as documents_router
from app.plugins.fleet.franchises.infrastructure.repository import (
    init_schema as init_franchise_schema,
)
from app.plugins.fleet.franchises.interfaces.router import router as franchise_router
from app.plugins.fleet.insurance.infrastructure.repository import (
    init_schema as init_insurance_schema,
)
from app.plugins.fleet.insurance.interfaces.router import router as insurance_router
from app.plugins.fleet.rentals.infrastructure.repository import init_schema as init_rental_schema
from app.plugins.fleet.rentals.interfaces.router import router as rental_router
from app.plugins.fleet.deadlines.interfaces.router import router as deadlines_router
from app.plugins.fleet.vision.router import router as vision_router


def fleet_plugin_enabled() -> bool:
    value = os.getenv("FLEET_PLUGIN_ENABLED", "true")
    return value.strip().casefold() not in {"0", "false", "no", "off"}


def initialize_fleet_plugin() -> None:
    if fleet_plugin_enabled():
        init_schema()
        init_sync_schema()
        init_journal_schema()
        init_damage_schema()
        init_maintenance_schema()
        init_documents_schema()
        init_franchise_schema()
        init_insurance_schema()
        init_rental_schema()


def register_fleet_plugin(app: FastAPI) -> None:
    if fleet_plugin_enabled():
        app.include_router(router)
        app.include_router(sync_router)
        app.include_router(journal_router)
        app.include_router(control_room_router)
        app.include_router(damage_router)
        app.include_router(maintenance_router)
        app.include_router(documents_router)
        app.include_router(franchise_router)
        app.include_router(insurance_router)
        app.include_router(rental_router)
        app.include_router(deadlines_router)
        app.include_router(vision_router)
