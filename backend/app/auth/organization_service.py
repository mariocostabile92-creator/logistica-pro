import sqlite3

from app.auth import repository
from app.auth.domain import AuthenticatedUser, Role
from app.auth.password_service import hash_password


class OrganizationError(Exception):
    def __init__(self, detail: str, status_code: int = 400):
        super().__init__(detail)
        self.status_code = status_code


def _user_payload(row) -> dict:
    return {
        "id": row["id"], "first_name": row["first_name"],
        "last_name": row["last_name"], "email": row["email"],
        "role": row["role"], "active": bool(row["active"]),
        "last_login_at": row["last_login_at"], "created_at": row["created_at"],
    }


def organization(user: AuthenticatedUser) -> dict:
    row = repository.organization_by_id(user.organization_id)
    if not row:
        raise OrganizationError("Organizzazione non trovata.", 404)
    return {
        "id": row["id"], "name": row["name"],
        "primary_station": row["primary_station"], "timezone": row["timezone"],
        "language": row["language"], "created_at": row["created_at"],
    }


def users(user: AuthenticatedUser) -> list[dict]:
    return [_user_payload(row) for row in repository.list_organization_users(user.organization_id)]


def create_user(actor: AuthenticatedUser, data: dict) -> dict:
    try:
        user_id = repository.create_organization_user(
            actor.organization_id, data, hash_password(data["temporary_password"])
        )
    except sqlite3.IntegrityError as exc:
        raise OrganizationError("Email gia utilizzata.", 409) from exc
    repository.record_audit(actor, "user.created", user_id, 201)
    return _user_payload(repository.organization_user(actor.organization_id, user_id))


def update_user(actor: AuthenticatedUser, user_id: str, data: dict) -> dict:
    current = repository.organization_user(actor.organization_id, user_id)
    if not current:
        raise OrganizationError("Utente non trovato.", 404)
    removing_last_admin = (
        current["role"] == Role.ADMINISTRATOR.value
        and bool(current["active"])
        and (data["role"] != Role.ADMINISTRATOR or not data["active"])
        and repository.active_administrator_count(actor.organization_id) <= 1
    )
    if removing_last_admin:
        raise OrganizationError("L'ultimo Administrator attivo non puo essere disattivato o declassato.", 409)
    repository.update_organization_user(actor.organization_id, user_id, data)
    action = "user.role_changed" if current["role"] != data["role"].value else (
        "user.reactivated" if data["active"] and not current["active"] else
        "user.deactivated" if not data["active"] and current["active"] else "user.updated"
    )
    repository.record_audit(actor, action, user_id, 200)
    return _user_payload(repository.organization_user(actor.organization_id, user_id))


def change_password(actor: AuthenticatedUser, user_id: str, password: str) -> None:
    if not repository.organization_user(actor.organization_id, user_id):
        raise OrganizationError("Utente non trovato.", 404)
    repository.update_user_password(actor.organization_id, user_id, hash_password(password))
    repository.record_audit(actor, "user.password_changed", user_id, 204)
