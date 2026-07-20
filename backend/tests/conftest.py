import os
import tempfile
import uuid
from pathlib import Path

import pytest


TEST_DATABASE_PATH = (
    Path(tempfile.gettempdir())
    / f"logistica-mvp-tests-{uuid.uuid4().hex}.sqlite3"
)
os.environ["OPERATIONS_DB_PATH"] = str(TEST_DATABASE_PATH)
os.environ.setdefault("DEMO_WORKSPACE_ENABLED", "true")

from app.core.database import db_session, init_db
from app.briefing.repository import init_schema as init_briefing_schema
from app.core.configuration.repository import (
    init_schema as init_configuration_schema,
)
from app.demo.repository import init_schema as init_demo_schema
from app.plugins.fleet.infrastructure.repository import init_schema as init_fleet_schema


@pytest.fixture(autouse=True)
def reset_database():
    init_db()
    init_configuration_schema()
    init_fleet_schema()
    init_briefing_schema()
    init_demo_schema()
    with db_session() as conn:
        conn.execute("DELETE FROM demo_workspaces")
        conn.execute("DELETE FROM configuration_versions")
        conn.execute("DELETE FROM fleet_asset_events")
        conn.execute("DELETE FROM fleet_asset_documents")
        conn.execute("DELETE FROM fleet_assets")
        conn.execute("DELETE FROM daily_briefings")
        conn.execute("DELETE FROM planning_events")
        conn.execute("DELETE FROM planning_versions")
        conn.execute("DELETE FROM assignments")
        conn.execute("DELETE FROM plannings")
        conn.execute("DELETE FROM operation_snapshots")
        conn.execute("DELETE FROM analyses")
        conn.execute("DELETE FROM imports")
    yield


@pytest.fixture(scope="session", autouse=True)
def remove_test_database():
    yield
    TEST_DATABASE_PATH.unlink(missing_ok=True)
