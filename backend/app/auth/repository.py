import hashlib
import secrets
import uuid
from datetime import UTC, datetime

from app.auth.domain import AuthenticatedUser, Role
from app.core.config import SETTINGS
from app.core.database import db_session


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


def init_schema() -> None:
    with db_session() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS organizations (
            id TEXT PRIMARY KEY, name TEXT NOT NULL, created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS auth_users (
            id TEXT PRIMARY KEY,
            organization_id TEXT NOT NULL,
            email TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL,
            active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (organization_id) REFERENCES organizations(id)
        );
        CREATE TABLE IF NOT EXISTS auth_sessions (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            token_hash TEXT NOT NULL UNIQUE,
            expires_at TEXT NOT NULL,
            remember_me INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            last_seen_at TEXT NOT NULL,
            revoked_at TEXT,
            FOREIGN KEY (user_id) REFERENCES auth_users(id)
        );
        CREATE TABLE IF NOT EXISTS admin_audit_events (
            id TEXT PRIMARY KEY,
            organization_id TEXT NOT NULL,
            user_id TEXT NOT NULL,
            action TEXT NOT NULL,
            target TEXT NOT NULL,
            status_code INTEGER NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS auth_bootstrap_state (
            id INTEGER PRIMARY KEY,
            completed_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_auth_sessions_token ON auth_sessions(token_hash);
        CREATE INDEX IF NOT EXISTS idx_audit_org_time ON admin_audit_events(organization_id, created_at);
        """)
        _ensure_column(conn, "organizations", "primary_station", "TEXT")
        _ensure_column(conn, "organizations", "timezone", "TEXT NOT NULL DEFAULT 'Europe/Rome'")
        _ensure_column(conn, "organizations", "operational_day_start_hour", "INTEGER NOT NULL DEFAULT 4")
        _ensure_column(conn, "organizations", "language", "TEXT NOT NULL DEFAULT 'it'")
        _ensure_column(conn, "organizations", "updated_at", "TEXT")
        _ensure_column(conn, "auth_users", "first_name", "TEXT NOT NULL DEFAULT ''")
        _ensure_column(conn, "auth_users", "last_name", "TEXT NOT NULL DEFAULT ''")
        _ensure_column(conn, "auth_users", "last_login_at", "TEXT")
        _ensure_column(conn, "auth_users", "deleted_at", "TEXT")


def _ensure_column(conn, table: str, column: str, definition: str) -> None:
    if SETTINGS.database_backend == "postgresql":
        rows = conn.execute(
            "SELECT column_name FROM information_schema.columns WHERE table_name=?",
            (table,),
        ).fetchall()
        columns = {row[0] for row in rows}
    else:
        rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
        columns = {row[1] for row in rows}
    if column not in columns:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def create_user(email: str, password_hash: str, role: Role, organization_name: str) -> str:
    user_id, organization_id, timestamp = str(uuid.uuid4()), str(uuid.uuid4()), now_iso()
    with db_session() as conn:
        conn.execute(
            "INSERT INTO organizations (id,name,created_at) VALUES (?,?,?)",
            (organization_id, organization_name, timestamp),
        )
        conn.execute(
            """INSERT INTO auth_users
            (id,organization_id,email,password_hash,role,active,created_at,updated_at)
            VALUES (?,?,?,?,?,1,?,?)""",
            (user_id, organization_id, email.casefold(), password_hash, role.value, timestamp, timestamp),
        )
    return user_id


def user_by_email(email: str):
    with db_session() as conn:
        return conn.execute(
            """SELECT u.*, o.name organization_name FROM auth_users u
            JOIN organizations o ON o.id=u.organization_id WHERE u.email=?""",
            (email.casefold(),),
        ).fetchone()


def create_session(user_id: str, expires_at: str, remember_me: bool) -> tuple[str, str]:
    session_id, token, timestamp = str(uuid.uuid4()), secrets.token_urlsafe(48), now_iso()
    with db_session() as conn:
        conn.execute(
            """INSERT INTO auth_sessions
            (id,user_id,token_hash,expires_at,remember_me,created_at,last_seen_at)
            VALUES (?,?,?,?,?,?,?)""",
            (session_id, user_id, hashlib.sha256(token.encode()).hexdigest(), expires_at, int(remember_me), timestamp, timestamp),
        )
    return session_id, token


def user_by_session(token: str) -> tuple[AuthenticatedUser, str] | None:
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    with db_session() as conn:
        row = conn.execute(
            """SELECT s.id session_id,s.expires_at,u.id,u.email,u.role,u.organization_id,
            u.first_name,u.last_name,o.name organization_name
            FROM auth_sessions s JOIN auth_users u ON u.id=s.user_id
            JOIN organizations o ON o.id=u.organization_id
            WHERE s.token_hash=? AND s.revoked_at IS NULL AND u.active=1""",
            (token_hash,),
        ).fetchone()
        if not row:
            return None
        if datetime.fromisoformat(row["expires_at"]) <= datetime.now(UTC):
            conn.execute(
                "UPDATE auth_sessions SET revoked_at=? WHERE id=? AND revoked_at IS NULL",
                (now_iso(), row["session_id"]),
            )
            return None
        conn.execute("UPDATE auth_sessions SET last_seen_at=? WHERE id=?", (now_iso(), row["session_id"]))
    return AuthenticatedUser(
        id=row["id"], email=row["email"], role=Role(row["role"]),
        organization_id=row["organization_id"], organization_name=row["organization_name"],
        first_name=row["first_name"], last_name=row["last_name"],
    ), row["session_id"]


def bootstrap_required() -> bool:
    with db_session() as conn:
        organization = conn.execute("SELECT 1 FROM organizations LIMIT 1").fetchone()
        administrator = conn.execute(
            "SELECT 1 FROM auth_users WHERE role=? AND active=1 LIMIT 1",
            (Role.ADMINISTRATOR.value,),
        ).fetchone()
    return not organization or not administrator


def create_initial_setup(organization: dict, administrator: dict, password_hash: str) -> str:
    organization_id, user_id, timestamp = str(uuid.uuid4()), str(uuid.uuid4()), now_iso()
    with db_session() as conn:
        conn.execute(
            "INSERT INTO auth_bootstrap_state (id,completed_at) VALUES (1,?)",
            (timestamp,),
        )
        if conn.execute(
            "SELECT 1 FROM auth_users WHERE role=? LIMIT 1", (Role.ADMINISTRATOR.value,)
        ).fetchone():
            raise RuntimeError("Bootstrap gia completato.")
        existing = conn.execute("SELECT id FROM organizations ORDER BY created_at LIMIT 1").fetchone()
        if existing:
            organization_id = existing["id"]
            conn.execute(
                """UPDATE organizations SET name=?,primary_station=?,timezone=?,language=?,updated_at=?
                WHERE id=?""",
                (organization["name"], organization.get("primary_station"), organization["timezone"],
                 organization["language"], timestamp, organization_id),
            )
        else:
            conn.execute(
                """INSERT INTO organizations
                (id,name,primary_station,timezone,language,created_at,updated_at)
                VALUES (?,?,?,?,?,?,?)""",
                (organization_id, organization["name"], organization.get("primary_station"),
                 organization["timezone"], organization["language"], timestamp, timestamp),
            )
        conn.execute(
            """INSERT INTO auth_users
            (id,organization_id,email,password_hash,role,active,created_at,updated_at,
             first_name,last_name)
            VALUES (?,?,?,?,?,1,?,?,?,?)""",
            (user_id, organization_id, administrator["email"].casefold(), password_hash,
             Role.ADMINISTRATOR.value, timestamp, timestamp,
             administrator["first_name"], administrator["last_name"]),
        )
    return user_id


def create_registered_organization(organization: dict, administrator: dict, password_hash: str) -> tuple[str, str]:
    organization_id, user_id, timestamp = str(uuid.uuid4()), str(uuid.uuid4()), now_iso()
    with db_session() as conn:
        if conn.execute(
            "SELECT 1 FROM auth_users WHERE email=? LIMIT 1",
            (administrator["email"].casefold(),),
        ).fetchone():
            raise RuntimeError("Email gia utilizzata.")
        conn.execute(
            """INSERT INTO organizations
            (id,name,primary_station,timezone,language,created_at,updated_at)
            VALUES (?,?,?,?,?,?,?)""",
            (organization_id, organization["name"].strip(), organization.get("primary_station"),
             organization["timezone"], organization["language"], timestamp, timestamp),
        )
        conn.execute(
            """INSERT INTO auth_users
            (id,organization_id,email,password_hash,role,active,created_at,updated_at,
             first_name,last_name)
            VALUES (?,?,?,?,?,1,?,?,?,?)""",
            (user_id, organization_id, administrator["email"].casefold(), password_hash,
             Role.ADMINISTRATOR.value, timestamp, timestamp,
             administrator["first_name"].strip(), administrator["last_name"].strip()),
        )
        conn.execute(
            """INSERT INTO admin_audit_events
            (id,organization_id,user_id,action,target,status_code,created_at)
            VALUES (?,?,?,?,?,?,?)""",
            (str(uuid.uuid4()), organization_id, user_id, "organization.registered",
             organization_id, 201, timestamp),
        )
    return organization_id, user_id


def organization_by_id(organization_id: str):
    with db_session() as conn:
        return conn.execute("SELECT * FROM organizations WHERE id=?", (organization_id,)).fetchone()


def list_organization_users(organization_id: str):
    with db_session() as conn:
        return conn.execute(
            """SELECT id,email,role,active,first_name,last_name,last_login_at,
            created_at,updated_at,deleted_at FROM auth_users
            WHERE organization_id=? ORDER BY active DESC,last_name,email""",
            (organization_id,),
        ).fetchall()


def organization_user(organization_id: str, user_id: str):
    with db_session() as conn:
        return conn.execute(
            "SELECT * FROM auth_users WHERE organization_id=? AND id=?",
            (organization_id, user_id),
        ).fetchone()


def create_organization_user(organization_id: str, data: dict, password_hash: str) -> str:
    user_id, timestamp = str(uuid.uuid4()), now_iso()
    with db_session() as conn:
        conn.execute(
            """INSERT INTO auth_users
            (id,organization_id,email,password_hash,role,active,created_at,updated_at,
             first_name,last_name)
            VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (user_id, organization_id, data["email"].casefold(), password_hash,
             data["role"].value, int(data["active"]), timestamp, timestamp,
             data["first_name"], data["last_name"]),
        )
    return user_id


def active_administrator_count(organization_id: str) -> int:
    with db_session() as conn:
        row = conn.execute(
            "SELECT COUNT(*) total FROM auth_users WHERE organization_id=? AND role=? AND active=1",
            (organization_id, Role.ADMINISTRATOR.value),
        ).fetchone()
    return int(row["total"])


def update_organization_user(organization_id: str, user_id: str, data: dict) -> None:
    timestamp = now_iso()
    with db_session() as conn:
        conn.execute(
            """UPDATE auth_users SET first_name=?,last_name=?,role=?,active=?,
            deleted_at=?,updated_at=? WHERE organization_id=? AND id=?""",
            (data["first_name"], data["last_name"], data["role"].value,
             int(data["active"]), None if data["active"] else timestamp,
             timestamp, organization_id, user_id),
        )
        if not data["active"]:
            conn.execute(
                "UPDATE auth_sessions SET revoked_at=? WHERE user_id=? AND revoked_at IS NULL",
                (timestamp, user_id),
            )


def update_user_password(organization_id: str, user_id: str, password_hash: str) -> None:
    timestamp = now_iso()
    with db_session() as conn:
        conn.execute(
            "UPDATE auth_users SET password_hash=?,updated_at=? WHERE organization_id=? AND id=?",
            (password_hash, timestamp, organization_id, user_id),
        )
        conn.execute(
            "UPDATE auth_sessions SET revoked_at=? WHERE user_id=? AND revoked_at IS NULL",
            (timestamp, user_id),
        )


def mark_login(user_id: str) -> None:
    with db_session() as conn:
        conn.execute("UPDATE auth_users SET last_login_at=? WHERE id=?", (now_iso(), user_id))


def revoke_session(session_id: str) -> None:
    with db_session() as conn:
        conn.execute("UPDATE auth_sessions SET revoked_at=? WHERE id=?", (now_iso(), session_id))


def record_audit(user: AuthenticatedUser, action: str, target: str, status_code: int) -> None:
    with db_session() as conn:
        conn.execute(
            "INSERT INTO admin_audit_events (id,organization_id,user_id,action,target,status_code,created_at) VALUES (?,?,?,?,?,?,?)",
            (str(uuid.uuid4()), user.organization_id, user.id, action, target, status_code, now_iso()),
        )
