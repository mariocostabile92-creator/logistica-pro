import json
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

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
    assert asset.headers["cache-control"] == "public, max-age=300"


def test_railway_configuration_and_secret_hygiene():
    railway = json.loads(
        (PROJECT_DIR / "railway.json").read_text(encoding="utf-8")
    )

    assert railway["build"]["builder"] == "DOCKERFILE"
    assert railway["deploy"]["healthcheckPath"] == "/api/health"
    assert "$PORT" in railway["deploy"]["startCommand"]
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
