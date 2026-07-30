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
os.environ.setdefault("WORKFORCE_PLUGIN_ENABLED", "true")

from app.core.database import db_session, init_db
from app.briefing.repository import init_schema as init_briefing_schema
from app.core.configuration.repository import (
    init_schema as init_configuration_schema,
)
from app.demo.repository import init_schema as init_demo_schema
from app.plugins.fleet.infrastructure.repository import init_schema as init_fleet_schema
from app.plugins.fleet.infrastructure.sync_schema import init_sync_schema as init_fleet_sync_schema
from app.plugins.fleet.journal.infrastructure.repository import (
    init_schema as init_journal_schema,
)
from app.plugins.fleet.damage.infrastructure.repository import (
    init_schema as init_damage_schema,
)
from app.plugins.fleet.maintenance.infrastructure.repository import (
    init_schema as init_maintenance_schema,
)
from app.plugins.workforce.infrastructure.schema import init_schema as init_workforce_schema
from app.repositories.authority_repository import init_schema as init_authority_schema
from app.repositories.execution_intent_repository import init_schema as init_execution_intent_schema
from app.repositories.execution_attempt_repository import init_schema as init_execution_attempt_schema
from app.repositories.planning_draft_repository import init_schema as init_planning_draft_schema
from app.repositories.planning_confirmation_repository import init_schema as init_planning_confirmation_schema
from app.repositories.planning_publication_repository import init_schema as init_planning_publication_schema
from app.workspace.repository import init_schema as init_workspace_schema


@pytest.fixture(autouse=True)
def reset_database():
    init_db()
    init_configuration_schema()
    init_fleet_schema()
    init_fleet_sync_schema()
    init_journal_schema()
    init_damage_schema()
    init_maintenance_schema()
    init_workforce_schema()
    init_briefing_schema()
    init_demo_schema()
    init_workspace_schema()
    init_planning_draft_schema()
    init_planning_confirmation_schema()
    init_planning_publication_schema()
    init_authority_schema()
    init_execution_intent_schema()
    init_execution_attempt_schema()
    with db_session() as conn:
        conn.execute("DELETE FROM fleet_maintenance_events")
        conn.execute("DELETE FROM fleet_maintenances")
        conn.execute("DELETE FROM damage_case_events")
        conn.execute("DELETE FROM damage_cases")
        conn.execute("DELETE FROM movement_media")
        conn.execute("DELETE FROM movement_equipment")
        conn.execute("DELETE FROM asset_movements")
        conn.execute("DELETE FROM journal_sessions")
        conn.execute("DELETE FROM workspace_reset_audits")
        conn.execute("DELETE FROM demo_workspaces")
        conn.execute("DELETE FROM configuration_versions")
        conn.execute("DELETE FROM workforce_changes")
        conn.execute("DELETE FROM workforce_day_statuses")
        conn.execute("DELETE FROM workforce_requirements")
        conn.execute("DELETE FROM workforce_members")
        conn.execute("DELETE FROM workforce_imports")
        conn.execute("DELETE FROM fleet_sync_event_fingerprints")
        conn.execute("DELETE FROM fleet_asset_events")
        conn.execute("DELETE FROM fleet_sync_runs")
        conn.execute("DELETE FROM fleet_asset_metadata")
        conn.execute("DELETE FROM fleet_asset_documents")
        conn.execute("DELETE FROM fleet_assets")
        conn.execute("DELETE FROM daily_briefings")
        conn.execute("DELETE FROM planning_publications")
        conn.execute("DELETE FROM runtime_execution_attempts")
        conn.execute("DELETE FROM runtime_execution_intents")
        conn.execute("DELETE FROM runtime_authority_decisions")
        conn.execute("DELETE FROM planning_confirmations")
        conn.execute("DELETE FROM planning_draft_changes")
        conn.execute("DELETE FROM planning_draft_versions")
        conn.execute("DELETE FROM planning_drafts")
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
