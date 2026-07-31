import hashlib
import secrets
import uuid
from datetime import UTC, datetime

from app.auth.domain import AuthenticatedUser, Role
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
        CREATE INDEX IF NOT EXISTS idx_auth_sessions_token ON auth_sessions(token_hash);
        CREATE INDEX IF NOT EXISTS idx_audit_org_time ON admin_audit_events(organization_id, created_at);
        """)


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
            """SELECT s.id session_id,s.expires_at,u.id,u.email,u.role,u.organization_id,o.name organization_name
            FROM auth_sessions s JOIN auth_users u ON u.id=s.user_id
            JOIN organizations o ON o.id=u.organization_id
            WHERE s.token_hash=? AND s.revoked_at IS NULL AND u.active=1""",
            (token_hash,),
        ).fetchone()
        if not row or datetime.fromisoformat(row["expires_at"]) <= datetime.now(UTC):
            return None
        conn.execute("UPDATE auth_sessions SET last_seen_at=? WHERE id=?", (now_iso(), row["session_id"]))
    return AuthenticatedUser(
        id=row["id"], email=row["email"], role=Role(row["role"]),
        organization_id=row["organization_id"], organization_name=row["organization_name"],
    ), row["session_id"]


def revoke_session(session_id: str) -> None:
    with db_session() as conn:
        conn.execute("UPDATE auth_sessions SET revoked_at=? WHERE id=?", (now_iso(), session_id))


def record_audit(user: AuthenticatedUser, action: str, target: str, status_code: int) -> None:
    with db_session() as conn:
        conn.execute(
            "INSERT INTO admin_audit_events (id,organization_id,user_id,action,target,status_code,created_at) VALUES (?,?,?,?,?,?,?)",
            (str(uuid.uuid4()), user.organization_id, user.id, action, target, status_code, now_iso()),
        )

