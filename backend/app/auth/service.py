import os
from datetime import UTC, datetime, timedelta

from app.auth import repository
from app.auth.domain import AuthenticatedUser, Role
from app.auth.password_service import hash_password, verify_password


SESSION_HOURS = 8
REMEMBER_DAYS = 30


class InvalidCredentialsError(Exception):
    pass


def bootstrap_user() -> None:
    email = os.environ.get("BOOTSTRAP_ADMIN_EMAIL", "").strip().casefold()
    password = os.environ.get("BOOTSTRAP_ADMIN_PASSWORD", "")
    if email and password and not repository.user_by_email(email):
        repository.create_user(
            email, hash_password(password), Role.ADMINISTRATOR,
            os.environ.get("BOOTSTRAP_ORGANIZATION", "Operations Engine"),
        )


def login(email: str, password: str, remember_me: bool) -> tuple[AuthenticatedUser, str, datetime]:
    row = repository.user_by_email(email)
    if not row or not row["active"] or not verify_password(password, row["password_hash"]):
        raise InvalidCredentialsError
    expires_at = datetime.now(UTC) + (
        timedelta(days=REMEMBER_DAYS) if remember_me else timedelta(hours=SESSION_HOURS)
    )
    _, token = repository.create_session(row["id"], expires_at.isoformat(), remember_me)
    repository.mark_login(row["id"])
    user = AuthenticatedUser(
        id=row["id"], email=row["email"], role=Role(row["role"]),
        organization_id=row["organization_id"], organization_name=row["organization_name"],
        first_name=row["first_name"], last_name=row["last_name"],
    )
    return user, token, expires_at
