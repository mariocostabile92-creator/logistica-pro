import json
import re
import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import start as server_start
from app.api.routers import health as health_router
from app.core.config import load_settings
from app.core.database import (
    DatabaseRow,
    PostgresConnection,
    _normalize_postgres_url,
    _postgres_schema_statement,
    _postgres_statement,
)
from app.main import app
from app.plugins.fleet.infrastructure.repository import (
    _ensure_asset_tenant_identity,
)
from app.plugins.workforce.infrastructure.schema import (
    _ensure_scoped_uniqueness,
)


PROJECT_DIR = Path(__file__).parents[2]
client = TestClient(app)


def production_environment(**overrides: str) -> dict[str, str]:
    values = {
        "APP_ENV": "production",
        "DEBUG": "false",
        "SECRET_KEY": "x" * 32,
        "BASE_URL": "https://operations.example",
        "API_URL": "https://operations.example",
        "DATABASE_URL": "postgresql://database.example/operations",
    }
    values.update(overrides)
    return values


def test_production_settings_require_secret_and_database():
    without_secret = production_environment()
    without_secret.pop("SECRET_KEY")
    with pytest.raises(ValueError, match="SECRET_KEY"):
        load_settings(without_secret)

    without_database = production_environment()
    without_database.pop("DATABASE_URL")
    with pytest.raises(ValueError, match="DATABASE_URL"):
        load_settings(without_database)

    without_base_url = production_environment()
    without_base_url.pop("BASE_URL")
    with pytest.raises(ValueError, match="BASE_URL"):
        load_settings(without_base_url)


def test_production_settings_are_safe_and_same_origin_by_default():
    settings = load_settings(production_environment())

    assert settings.production is True
    assert settings.debug is False
    assert settings.cors_origins == ("https://operations.example",)
    assert settings.max_upload_size_bytes == 8 * 1024 * 1024


def test_production_settings_reject_debug_and_wildcard_cors():
    with pytest.raises(ValueError, match="DEBUG"):
        load_settings(production_environment(DEBUG="true"))
    with pytest.raises(ValueError, match="CORS_ORIGINS"):
        load_settings(production_environment(CORS_ORIGINS="*"))
    with pytest.raises(ValueError, match="PostgreSQL"):
        load_settings(
            production_environment(DATABASE_URL="sqlite:///production.sqlite3")
        )


def test_database_url_and_sql_are_translated_for_postgres():
    assert _normalize_postgres_url(
        "postgres://database.example/operations"
    ) == "postgresql://database.example/operations"
    assert _normalize_postgres_url("sqlite:///local.sqlite3") is None

    query, returns_identity = _postgres_statement(
        "INSERT INTO imports (dataset_type) VALUES (?)"
    )
    assert "VALUES (%s)" in query
    assert query.endswith("RETURNING id")
    assert returns_identity is True
    assert "SERIAL PRIMARY KEY" in _postgres_schema_statement(
        "id INTEGER PRIMARY KEY AUTOINCREMENT"
    )


def test_postgres_compatibility_cursor_preserves_lastrowid():
    class FakeCursor:
        description = ()

        def __init__(self):
            self.query = ""

        def execute(self, query, parameters):
            self.query = query
            self.parameters = parameters

        def fetchone(self):
            return (41,)

        def fetchall(self):
            return []

    class FakeConnection:
        def __init__(self):
            self.cursor_instance = FakeCursor()

        def cursor(self):
            return self.cursor_instance

    raw_connection = FakeConnection()
    connection = PostgresConnection(raw_connection)
    cursor = connection.execute(
        "INSERT INTO analyses (created_at, summary, conflicts) VALUES (?, ?, ?)",
        ("now", "{}", "[]"),
    )

    assert cursor.lastrowid == 41
    assert raw_connection.cursor_instance.query.endswith("RETURNING id")
    assert raw_connection.cursor_instance.parameters == ("now", "{}", "[]")


@pytest.mark.parametrize(
    "table",
    (
        "fleet_franchise_cases",
        "fleet_insurance_policies",
        "fleet_maintenances",
        "fleet_rentals",
        "fleet_vehicle_documents",
    ),
)
def test_postgres_fleet_insert_preserves_lastrowid(table):
    query, returns_identity = _postgres_statement(
        f"INSERT INTO {table} (vehicle_id) VALUES (?)"
    )

    assert returns_identity is True
    assert "VALUES (%s)" in query
    assert query.endswith("RETURNING id")


def test_postgres_fleet_identity_is_scoped_to_the_organization():
    statements = []

    class RecordingConnection:
        @staticmethod
        def execute(statement, parameters=()):
            statements.append((" ".join(statement.split()), parameters))

    _ensure_asset_tenant_identity(RecordingConnection(), "postgresql")

    sql = "\n".join(statement for statement, _ in statements)
    assert "DROP CONSTRAINT IF EXISTS fleet_assets_external_identifier_key" in sql
    assert "DROP CONSTRAINT IF EXISTS fleet_assets_plate_key" in sql
    assert "fleet_assets(organization_id, LOWER(external_identifier))" in sql
    assert "fleet_assets(organization_id, LOWER(plate))" in sql


def test_postgres_workforce_identity_is_scoped_to_the_organization():
    statements = []

    class RecordingConnection:
        @staticmethod
        def execute(statement, parameters=()):
            statements.append((" ".join(statement.split()), parameters))

    _ensure_scoped_uniqueness(RecordingConnection(), "postgresql")

    sql = "\n".join(statement for statement, _ in statements)
    assert "workforce_members_external_identifier_key" in sql
    assert "workforce_imports_fingerprint_key" in sql
    assert "workforce_requirements_date_operational_unit_id_key" in sql
    assert "workforce_members(organization_id, LOWER(external_identifier))" in sql
    assert "workforce_imports(organization_id, fingerprint)" in sql
    assert (
        "workforce_requirements(organization_id, date, operational_unit_id)"
        in sql
    )


def test_sqlite_fleet_identity_migration_preserves_data_and_references():
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    connection.executescript(
        """
        PRAGMA foreign_keys = ON;
        CREATE TABLE fleet_assets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            organization_id TEXT,
            external_identifier TEXT NOT NULL UNIQUE,
            plate TEXT UNIQUE,
            category TEXT,
            status TEXT NOT NULL,
            availability TEXT NOT NULL,
            notes TEXT,
            capabilities TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE fleet_asset_children (
            id INTEGER PRIMARY KEY,
            asset_id INTEGER NOT NULL REFERENCES fleet_assets(id)
        );
        INSERT INTO fleet_assets (
            organization_id, external_identifier, plate, status, availability,
            capabilities, created_at, updated_at
        ) VALUES ('org-a', 'SHARED-ASSET', 'SH001AA', 'active', 'available',
                  '[]', '2026-08-06', '2026-08-06');
        INSERT INTO fleet_asset_children (id, asset_id) VALUES (1, 1);
        """
    )

    _ensure_asset_tenant_identity(connection, "sqlite")

    assert connection.execute(
        "SELECT external_identifier FROM fleet_assets WHERE id = 1"
    ).fetchone()["external_identifier"] == "SHARED-ASSET"
    assert connection.execute(
        "PRAGMA foreign_key_list(fleet_asset_children)"
    ).fetchone()["table"] == "fleet_assets"
    connection.execute(
        """
        INSERT INTO fleet_assets (
            organization_id, external_identifier, plate, status, availability,
            capabilities, created_at, updated_at
        ) VALUES (?, ?, ?, 'active', 'available', '[]', '2026-08-06', '2026-08-06')
        """,
        ("org-b", "SHARED-ASSET", "SH001AA"),
    )
    with pytest.raises(sqlite3.IntegrityError):
        connection.execute(
            """
            INSERT INTO fleet_assets (
                organization_id, external_identifier, plate, status, availability,
                capabilities, created_at, updated_at
            ) VALUES (?, ?, ?, 'active', 'available', '[]', '2026-08-06', '2026-08-06')
            """,
            ("org-a", "shared-asset", "sh001aa"),
        )
    connection.close()


def test_database_row_supports_sqlite_compatible_access():
    row = DatabaseRow(("total", "status"), (3, "ready"))

    assert row[0] == 3
    assert row["status"] == "ready"
    assert row.keys() == ("total", "status")


def test_health_returns_unavailable_when_database_is_down(monkeypatch):
    monkeypatch.setattr(health_router, "database_is_ready", lambda: False)

    response = client.get("/api/health")

    assert response.status_code == 503
    assert "temporaneamente" in response.json()["detail"]


def test_frontend_is_served_same_origin_with_security_headers():
    response = client.get("/app/")

    assert response.status_code == 200
    assert "DSP Operations OS" in response.text
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert "default-src 'self'" in response.headers["content-security-policy"]
    assert response.headers["cache-control"] == "no-cache"

    asset = client.get("/app/assets/js/api.js")
    assert asset.status_code == 200
    assert "127.0.0.1:8000" not in asset.text
    # Source modules are not content-hashed, so they must be revalidated on
    # every release to prevent mixed JS/CSS versions after a deploy.
    assert asset.headers["cache-control"] == "no-cache"

    versioned_asset = client.get("/app/assets/js/api.js?v=34")
    assert versioned_asset.status_code == 200
    assert versioned_asset.headers["cache-control"] == (
        "public, max-age=31536000, immutable"
    )


def test_root_redirects_to_frontend_and_public_entrypoints_remain_available():
    response = client.get("/", follow_redirects=False)

    assert response.status_code == 307
    assert response.headers["location"] == "/app/"
    assert client.get("/api/health").status_code == 200
    assert client.get("/app/").status_code == 200


def test_railway_configuration_and_secret_hygiene():
    railway = json.loads(
        (PROJECT_DIR / "railway.json").read_text(encoding="utf-8")
    )
    dockerfile = (PROJECT_DIR / "Dockerfile").read_text(encoding="utf-8")
    procfile = (PROJECT_DIR / "Procfile").read_text(encoding="utf-8").strip()

    assert railway["build"]["builder"] == "DOCKERFILE"
    assert railway["deploy"]["healthcheckPath"] == "/api/health"
    assert railway["deploy"]["startCommand"] == (
        "/usr/local/bin/operations-entrypoint sh -c \"exec python -m uvicorn app.main:app --host 0.0.0.0 "
        "--port ${PORT:-8000} --proxy-headers "
        "--forwarded-allow-ips '*'\""
    )
    assert 'CMD ["python", "-m", "app.start"]' in dockerfile
    assert "EXPOSE 8000" not in dockerfile
    assert "${PORT:-8000}" not in dockerfile
    assert procfile == "web: cd backend && python -m app.start"
    assert not (PROJECT_DIR / "backend" / ".env").exists()
    assert not (PROJECT_DIR / "backend" / ".env.txt").exists()
    assert (PROJECT_DIR / "backend" / ".env.example").exists()
    for filename in (
        "users.json",
        "report_consegne.json",
        "storico_giri.json",
    ):
        assert json.loads(
            (PROJECT_DIR / "backend" / filename).read_text(encoding="utf-8")
        ) == []


def test_server_start_uses_validated_environment_port(monkeypatch):
    captured = {}
    monkeypatch.setenv("PORT", "43127")
    monkeypatch.setattr(
        server_start.uvicorn,
        "run",
        lambda application, **options: captured.update(
            application=application,
            **options,
        ),
    )

    server_start.main()

    assert captured == {
        "application": "app.main:app",
        "host": "0.0.0.0",
        "port": 43127,
        "proxy_headers": True,
        "forwarded_allow_ips": "*",
    }


@pytest.mark.parametrize(
    "environ",
    (
        {},
        {"PORT": ""},
        {"PORT": "$PORT"},
        {"PORT": "0"},
        {"PORT": "65536"},
    ),
)
def test_server_start_rejects_missing_or_invalid_port(environ):
    with pytest.raises(ValueError, match="PORT"):
        server_start.port_from_environment(environ)


def test_repository_has_no_recognizable_secret_literals():
    patterns = (
        re.compile(
            "postgres(?:ql)?://"
            r"[^\s\"']+:[^\s\"']+@",
            re.IGNORECASE,
        ),
        re.compile("sk-" + r"[A-Za-z0-9_-]{16,}"),
        re.compile("gh" + r"[pousr]_[A-Za-z0-9]{20,}"),
    )
    searchable_suffixes = {
        ".css",
        ".example",
        ".html",
        ".js",
        ".json",
        ".md",
        ".py",
        ".txt",
    }
    ignored_parts = {
        ".git",
        ".venv",
        ".pytest_cache",
        "__pycache__",
        "data",
        "venv",
    }
    violations = []

    for path in PROJECT_DIR.rglob("*"):
        if (
            not path.is_file()
            or ignored_parts.intersection(path.parts)
            or path.suffix.casefold() not in searchable_suffixes
        ):
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        if any(pattern.search(text) for pattern in patterns):
            violations.append(str(path.relative_to(PROJECT_DIR)))

    assert violations == []
