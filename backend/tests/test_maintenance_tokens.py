import io
import json
from datetime import UTC, date, datetime, timedelta
from hashlib import sha256

from fastapi.testclient import TestClient
from openpyxl import Workbook

from app.auth.domain import Role
from app.auth.password_service import hash_password
from app.auth.repository import create_user
from app.core.database import db_session
from app.main import app
from app.plugins.workforce.importer.workbook_interpreter import (
    interpret_workforce_workbook,
)


ENFORCE = {"X-Auth-Enforce": "1"}
PASSWORD = "Password-sicura-123"
TOKEN_ENDPOINT = "/api/admin/maintenance-tokens"
COVERAGE_ENDPOINT = "/api/plugins/workforce/v1/planning/coverage"
PREVIEW_ENDPOINT = f"{COVERAGE_ENDPOINT}/backfill/preview"
APPLY_ENDPOINT = f"{COVERAGE_ENDPOINT}/backfill"
SCOPE = "PLANNING_COVERAGE_BACKFILL"
CYCLE_SCOPE = "WORKFORCE_OPERATIONAL_CYCLE_BACKFILL"
CYCLE_PREVIEW_ENDPOINT = (
    "/api/plugins/workforce/v1/operational-cycle-backfill/preview"
)
CYCLE_APPLY_ENDPOINT = "/api/plugins/workforce/v1/operational-cycle-backfill"


def _authenticated(role: Role, email: str):
    create_user(email, hash_password(PASSWORD), role, f"Org {email}")
    client = TestClient(app, headers=ENFORCE)
    login = client.post(
        "/api/auth/login",
        json={"email": email, "password": PASSWORD, "remember_me": False},
    )
    assert login.status_code == 200, login.text
    return client, login.json()["user"]["organization"]["id"]


def _create_token(
    client: TestClient,
    ttl_minutes: int = 15,
    scope: str = SCOPE,
):
    response = client.post(
        TOKEN_ENDPOINT,
        json={"scope": scope, "ttl_minutes": ttl_minutes},
    )
    assert response.status_code == 201, response.text
    return response


def _token_client(raw_token: str) -> TestClient:
    return TestClient(
        app,
        headers={
            **ENFORCE,
            "Authorization": f"Bearer {raw_token}",
        },
    )


def _workbook() -> bytes:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Planning"
    sheet["H13"] = "FORECAST"
    sheet["H14"] = 0.1
    sheet["H19"] = "FORECAST SAME DAY A"
    sheet["H20"] = "FORECAST SAME DAY B - C"
    sheet["G24"] = "Turno"
    sheet["H24"] = "drivers"
    sheet["L24"] = date(2026, 8, 10)
    sheet["L13"] = 76
    sheet["L19"] = 20
    sheet["L20"] = 18
    output = io.BytesIO()
    workbook.save(output)
    workbook.close()
    return output.getvalue()


def _cycle_workbook() -> bytes:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Planning"
    sheet["D24"] = "T-ID"
    sheet["G24"] = "Turno"
    sheet["H24"] = "drivers"
    sheet["D25"] = "T-CYCLE-1"
    sheet["G25"] = "NEXT"
    sheet["H25"] = "Cycle Driver"
    output = io.BytesIO()
    workbook.save(output)
    workbook.close()
    return output.getvalue()


def _legacy_import(content: bytes, organization_id: str) -> int:
    with db_session() as conn:
        cursor = conn.execute(
            """
            INSERT INTO workforce_imports (
                fingerprint, original_filename, imported_at, sheets,
                summary, organization_id
            ) VALUES (?, 'Planning legacy.xlsx', ?, '[]', '{}', ?)
            """,
            (
                sha256(content).hexdigest(),
                "2026-08-08T10:23:10+00:00",
                organization_id,
            ),
        )
        return int(cursor.lastrowid)


def _files(content: bytes):
    return {
        "file": (
            "Planning legacy.xlsx",
            content,
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    }


def _cycle_fixture(organization_id: str):
    content = _cycle_workbook()
    import_id = _legacy_import(content, organization_id)
    parsed = interpret_workforce_workbook(content, "Planning legacy.xlsx")
    source = next(
        row for row in parsed.source_rows
        if row.source_sheet == "Planning" and row.row_kind == "identity"
    )
    now = datetime.now(UTC).isoformat()
    with db_session() as conn:
        cursor = conn.execute(
            """
            INSERT INTO workforce_members (
                external_identifier, display_name, capabilities, active,
                source_reference, created_at, updated_at, organization_id,
                operational_cycle
            ) VALUES (?, ?, '[]', 1, 'legacy-planning', ?, ?, ?, 'NOT_SET')
            """,
            (
                source.resolution_identifier,
                source.driver_display_name,
                now,
                now,
                organization_id,
            ),
        )
        member_id = int(cursor.lastrowid)
    return content, import_id, member_id


def test_admin_creates_short_lived_hashed_token_with_no_store_and_audit():
    admin, organization_id = _authenticated(
        Role.ADMINISTRATOR, "maintenance-admin@example.test"
    )
    response = _create_token(admin)
    body = response.json()
    assert body["scope"] == SCOPE
    assert body["token"].startswith("omt_v1_")
    assert response.headers["cache-control"] == "no-store, private, max-age=0"
    assert response.headers["pragma"] == "no-cache"
    expires = datetime.fromisoformat(body["expires_at"])
    assert timedelta(minutes=14) < expires - datetime.now(UTC) <= timedelta(minutes=15)

    with db_session() as conn:
        row = conn.execute(
            "SELECT * FROM maintenance_tokens WHERE id = ?", (body["id"],)
        ).fetchone()
        audit = conn.execute(
            """
            SELECT * FROM admin_audit_events
            WHERE action = 'maintenance_token_created'
            """
        ).fetchone()
    assert row["organization_id"] == organization_id
    assert row["token_hash"] != body["token"]
    assert body["token"] not in json.dumps(dict(row))
    assert row["status"] == "ACTIVE"
    assert audit["organization_id"] == organization_id
    assert body["token"] not in audit["target"]
    assert row["token_hash"] not in response.text


def test_non_admin_and_invalid_ttl_are_rejected():
    viewer, _ = _authenticated(Role.VIEWER, "maintenance-viewer@example.test")
    denied = viewer.post(
        TOKEN_ENDPOINT, json={"scope": SCOPE, "ttl_minutes": 15}
    )
    assert denied.status_code == 403

    admin, _ = _authenticated(Role.ADMINISTRATOR, "maintenance-ttl@example.test")
    assert admin.post(
        TOKEN_ENDPOINT, json={"scope": SCOPE, "ttl_minutes": 31}
    ).status_code == 422


def test_no_more_than_five_active_tokens_can_be_created_per_organization():
    admin, _ = _authenticated(Role.ADMINISTRATOR, "maintenance-limit@example.test")
    for _ in range(5):
        assert _create_token(admin).status_code == 201
    limited = admin.post(
        TOKEN_ENDPOINT, json={"scope": SCOPE, "ttl_minutes": 15}
    )
    assert limited.status_code == 409
    assert "cinque token" in limited.json()["detail"]


def test_valid_token_reads_coverage_and_unrelated_endpoint_is_rejected():
    admin, _ = _authenticated(Role.ADMINISTRATOR, "maintenance-read@example.test")
    raw = _create_token(admin).json()["token"]
    technical = _token_client(raw)
    allowed = technical.get(
        COVERAGE_ENDPOINT,
        params={"date_from": "2026-08-10", "date_to": "2026-08-10"},
    )
    assert allowed.status_code == 200, allowed.text
    assert technical.get("/api/fleet/vision").status_code == 401
    with db_session() as conn:
        token = conn.execute("SELECT used_at FROM maintenance_tokens").fetchone()
        audit = conn.execute(
            """
            SELECT target FROM admin_audit_events
            WHERE action = 'maintenance_token_used'
            """
        ).fetchone()
    assert token["used_at"] is not None
    assert f"GET {COVERAGE_ENDPOINT}" in audit["target"]


def test_wrong_scope_expired_and_random_tokens_fail_with_generic_error():
    admin, _ = _authenticated(Role.ADMINISTRATOR, "maintenance-invalid@example.test")
    raw = _create_token(admin).json()["token"]
    with db_session() as conn:
        conn.execute("UPDATE maintenance_tokens SET scope = 'UNRELATED'")
    wrong_scope = _token_client(raw).get(
        COVERAGE_ENDPOINT,
        params={"date_from": "2026-08-10", "date_to": "2026-08-10"},
    )
    assert wrong_scope.status_code == 401
    assert wrong_scope.json() == {
        "detail": "Credenziali di manutenzione non valide."
    }

    with db_session() as conn:
        conn.execute(
            """
            UPDATE maintenance_tokens SET scope = ?, expires_at = ?, status = 'ACTIVE'
            """,
            (
                SCOPE,
                (datetime.now(UTC) - timedelta(minutes=1)).isoformat(),
            ),
        )
    expired = _token_client(raw).get(
        COVERAGE_ENDPOINT,
        params={"date_from": "2026-08-10", "date_to": "2026-08-10"},
    )
    assert expired.status_code == 401
    with db_session() as conn:
        row = conn.execute("SELECT status FROM maintenance_tokens").fetchone()
        audit = conn.execute(
            """
            SELECT action FROM admin_audit_events
            WHERE action = 'maintenance_token_expired'
            """
        ).fetchone()
    assert row["status"] == "EXPIRED"
    assert audit["action"] == "maintenance_token_expired"
    assert _token_client("omt_v1_not-a-token").get(
        COVERAGE_ENDPOINT,
        params={"date_from": "2026-08-10", "date_to": "2026-08-10"},
    ).status_code == 401


def test_revocation_is_immediate_audited_and_organization_scoped():
    first, _ = _authenticated(Role.ADMINISTRATOR, "maintenance-first@example.test")
    created = _create_token(first).json()
    second, _ = _authenticated(Role.ADMINISTRATOR, "maintenance-second@example.test")
    foreign = second.post(f"{TOKEN_ENDPOINT}/{created['id']}/revoke")
    assert foreign.status_code == 404
    assert _token_client(created["token"]).get(
        COVERAGE_ENDPOINT,
        params={"date_from": "2026-08-10", "date_to": "2026-08-10"},
    ).status_code == 200

    revoked = first.post(f"{TOKEN_ENDPOINT}/{created['id']}/revoke")
    assert revoked.status_code == 204
    assert _token_client(created["token"]).get(
        COVERAGE_ENDPOINT,
        params={"date_from": "2026-08-10", "date_to": "2026-08-10"},
    ).status_code == 401
    with db_session() as conn:
        row = conn.execute(
            "SELECT status, revoked_at FROM maintenance_tokens WHERE id = ?",
            (created["id"],),
        ).fetchone()
        audit = conn.execute(
            """
            SELECT * FROM admin_audit_events
            WHERE action = 'maintenance_token_revoked'
            """
        ).fetchone()
    assert row["status"] == "REVOKED" and row["revoked_at"]
    assert audit is not None


def test_token_uses_creator_organization_for_coverage_data():
    admin, organization_id = _authenticated(
        Role.ADMINISTRATOR, "maintenance-isolation@example.test"
    )
    raw = _create_token(admin).json()["token"]
    now = datetime.now(UTC).isoformat()
    with db_session() as conn:
        for org, forecast in ((organization_id, 12), ("foreign-org", 999)):
            conn.execute(
                """
                INSERT INTO workforce_daily_coverage_requirements (
                    organization_id, operational_date, station, station_key,
                    operational_cycle, coverage_segment, forecast_routes,
                    reserve_percentage, required_capacity, source,
                    source_reference, source_identity, created_at, updated_at
                ) VALUES (?, '2026-08-10', NULL, '', 'NEXT_DAY', '', ?, 10,
                          ?, 'IMPORT', 'qa', ?, ?, ?)
                """,
                (org, forecast, int(forecast * 1.1), f"source:{org}", now, now),
            )
    response = _token_client(raw).get(
        COVERAGE_ENDPOINT,
        params={"date_from": "2026-08-10", "date_to": "2026-08-10"},
    )
    assert response.status_code == 200
    next_day = next(
        item for item in response.json()["items"] if item["cycle"] == "NEXT_DAY"
    )
    assert next_day["forecast_routes"] == 12


def test_token_allows_real_coverage_preview_and_apply_only_for_its_org():
    admin, organization_id = _authenticated(
        Role.ADMINISTRATOR, "maintenance-backfill@example.test"
    )
    raw = _create_token(admin).json()["token"]
    content = _workbook()
    import_id = _legacy_import(content, organization_id)
    technical = _token_client(raw)
    preview = technical.post(
        PREVIEW_ENDPOINT,
        data={"workforce_import_id": str(import_id)},
        files=_files(content),
    )
    assert preview.status_code == 200, preview.text
    assert preview.json()["status"] == "READY"
    assert preview.json()["requirements_expected"] == 3

    applied = technical.post(
        APPLY_ENDPOINT,
        data={
            "workforce_import_id": str(import_id),
            "expected_preview_fingerprint": preview.json()["preview_fingerprint"],
        },
        files=_files(content),
    )
    assert applied.status_code == 200, applied.text
    assert applied.json()["requirements_created"] == 3
    with db_session() as conn:
        rows = conn.execute(
            """
            SELECT organization_id FROM workforce_daily_coverage_requirements
            """
        ).fetchall()
    assert {row["organization_id"] for row in rows} == {organization_id}


def test_valid_admin_session_takes_precedence_over_bad_bearer():
    admin, _ = _authenticated(Role.ADMINISTRATOR, "maintenance-precedence@example.test")
    response = admin.get(
        COVERAGE_ENDPOINT,
        params={"date_from": "2026-08-10", "date_to": "2026-08-10"},
        headers={"Authorization": "Bearer invalid"},
    )
    assert response.status_code == 200


def test_admin_creates_dedicated_cycle_scope_without_secret_leak():
    admin, organization_id = _authenticated(
        Role.ADMINISTRATOR, "cycle-scope-admin@example.test"
    )
    response = _create_token(admin, scope=CYCLE_SCOPE)
    body = response.json()
    assert body["scope"] == CYCLE_SCOPE
    with db_session() as conn:
        row = conn.execute(
            "SELECT * FROM maintenance_tokens WHERE id = ?", (body["id"],)
        ).fetchone()
        audit = conn.execute(
            """
            SELECT target FROM admin_audit_events
            WHERE action = 'maintenance_token_created'
            """
        ).fetchone()
    assert row["organization_id"] == organization_id
    assert row["scope"] == CYCLE_SCOPE
    assert row["token_hash"] != body["token"]
    assert body["token"] not in json.dumps(dict(row))
    assert body["token"] not in audit["target"]
    assert row["token_hash"] not in response.text
    assert f"scope:{CYCLE_SCOPE}" in audit["target"]


def test_cycle_scope_allows_preview_and_apply_for_creator_organization():
    admin, organization_id = _authenticated(
        Role.ADMINISTRATOR, "cycle-apply-admin@example.test"
    )
    raw = _create_token(admin, scope=CYCLE_SCOPE).json()["token"]
    content, import_id, member_id = _cycle_fixture(organization_id)
    technical = _token_client(raw)
    preview = technical.post(
        CYCLE_PREVIEW_ENDPOINT,
        data={"workforce_import_id": str(import_id)},
        files=_files(content),
    )
    assert preview.status_code == 200, preview.text
    assert preview.json()["summary"]["apply_eligible"] == 1
    applied = technical.post(
        CYCLE_APPLY_ENDPOINT,
        data={
            "workforce_import_id": str(import_id),
            "expected_preview_fingerprint": preview.json()[
                "preview_fingerprint"
            ],
        },
        files=_files(content),
    )
    assert applied.status_code == 200, applied.text
    assert applied.json()["members_updated"] == 1
    with db_session() as conn:
        member = conn.execute(
            """
            SELECT operational_cycle FROM workforce_members
            WHERE id = ? AND organization_id = ?
            """,
            (member_id, organization_id),
        ).fetchone()
        usage = conn.execute(
            """
            SELECT target FROM admin_audit_events
            WHERE action = 'maintenance_token_used'
            ORDER BY created_at DESC LIMIT 1
            """
        ).fetchone()
    assert member["operational_cycle"] == "NEXT_DAY"
    assert f"scope:{CYCLE_SCOPE}" in usage["target"]
    assert f"POST {CYCLE_APPLY_ENDPOINT}" in usage["target"]


def test_maintenance_scopes_are_strictly_separated_and_unrelated_is_denied():
    admin, organization_id = _authenticated(
        Role.ADMINISTRATOR, "cycle-cross-scope@example.test"
    )
    content, import_id, _ = _cycle_fixture(organization_id)
    coverage_token = _create_token(admin, scope=SCOPE).json()["token"]
    cycle_token = _create_token(admin, scope=CYCLE_SCOPE).json()["token"]

    coverage_on_cycle = _token_client(coverage_token).post(
        CYCLE_PREVIEW_ENDPOINT,
        data={"workforce_import_id": str(import_id)},
        files=_files(content),
    )
    assert coverage_on_cycle.status_code == 401

    cycle_on_coverage = _token_client(cycle_token).get(
        COVERAGE_ENDPOINT,
        params={"date_from": "2026-08-10", "date_to": "2026-08-10"},
    )
    assert cycle_on_coverage.status_code == 401
    assert _token_client(cycle_token).get(
        "/api/plugins/workforce/v1/members"
    ).status_code == 401
    assert _token_client(cycle_token).get("/api/fleet/vision").status_code == 401
    assert _token_client(cycle_token).post(
        TOKEN_ENDPOINT,
        json={"scope": CYCLE_SCOPE, "ttl_minutes": 15},
    ).status_code == 401


def test_cycle_scope_is_organization_scoped_and_never_accepts_foreign_import():
    admin, organization_id = _authenticated(
        Role.ADMINISTRATOR, "cycle-org-scope@example.test"
    )
    raw = _create_token(admin, scope=CYCLE_SCOPE).json()["token"]
    content, foreign_import, foreign_member = _cycle_fixture("foreign-org")
    response = _token_client(raw).post(
        CYCLE_PREVIEW_ENDPOINT,
        data={"workforce_import_id": str(foreign_import)},
        files=_files(content),
    )
    assert response.status_code == 422
    with db_session() as conn:
        member = conn.execute(
            "SELECT operational_cycle, organization_id FROM workforce_members WHERE id = ?",
            (foreign_member,),
        ).fetchone()
    assert organization_id != member["organization_id"]
    assert member["operational_cycle"] == "NOT_SET"


def test_expired_and_revoked_cycle_tokens_are_rejected_and_audited():
    admin, organization_id = _authenticated(
        Role.ADMINISTRATOR, "cycle-lifecycle@example.test"
    )
    content, import_id, _ = _cycle_fixture(organization_id)
    expired = _create_token(admin, scope=CYCLE_SCOPE).json()
    with db_session() as conn:
        conn.execute(
            "UPDATE maintenance_tokens SET expires_at = ? WHERE id = ?",
            (
                (datetime.now(UTC) - timedelta(minutes=1)).isoformat(),
                expired["id"],
            ),
        )
    assert _token_client(expired["token"]).post(
        CYCLE_PREVIEW_ENDPOINT,
        data={"workforce_import_id": str(import_id)},
        files=_files(content),
    ).status_code == 401

    revoked = _create_token(admin, scope=CYCLE_SCOPE).json()
    assert admin.post(f"{TOKEN_ENDPOINT}/{revoked['id']}/revoke").status_code == 204
    assert _token_client(revoked["token"]).post(
        CYCLE_PREVIEW_ENDPOINT,
        data={"workforce_import_id": str(import_id)},
        files=_files(content),
    ).status_code == 401
    with db_session() as conn:
        actions = {
            row["action"] for row in conn.execute(
                """
                SELECT action FROM admin_audit_events
                WHERE action IN (
                    'maintenance_token_expired',
                    'maintenance_token_revoked'
                )
                """
            ).fetchall()
        }
    assert actions == {
        "maintenance_token_expired", "maintenance_token_revoked"
    }


def test_valid_session_precedes_cycle_token_and_maintenance_needs_no_session():
    admin, organization_id = _authenticated(
        Role.ADMINISTRATOR, "cycle-session-admin@example.test"
    )
    content, import_id, _ = _cycle_fixture(organization_id)
    admin_response = admin.post(
        CYCLE_PREVIEW_ENDPOINT,
        data={"workforce_import_id": str(import_id)},
        files=_files(content),
        headers={"Authorization": "Bearer invalid"},
    )
    assert admin_response.status_code == 200, admin_response.text

    cycle_token = _create_token(admin, scope=CYCLE_SCOPE).json()["token"]
    viewer, _ = _authenticated(
        Role.VIEWER, "cycle-session-viewer@example.test"
    )
    viewer_response = viewer.post(
        CYCLE_PREVIEW_ENDPOINT,
        data={"workforce_import_id": str(import_id)},
        files=_files(content),
        headers={"Authorization": f"Bearer {cycle_token}"},
    )
    assert viewer_response.status_code == 403
