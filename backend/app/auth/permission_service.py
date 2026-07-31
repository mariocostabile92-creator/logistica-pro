from app.auth.domain import Role


ROLE_PERMISSIONS: dict[Role, frozenset[str]] = {
    Role.ADMINISTRATOR: frozenset({"admin:read", "admin:write", "users:manage"}),
    Role.OPERATIONS_MANAGER: frozenset({"admin:read", "admin:write"}),
    Role.FLEET_MANAGER: frozenset({"admin:read", "admin:write"}),
    Role.DISPATCHER: frozenset({"admin:read", "admin:write"}),
    Role.VIEWER: frozenset({"admin:read"}),
}


def has_permission(role: Role, permission: str) -> bool:
    return permission in ROLE_PERMISSIONS.get(role, frozenset())


def permissions_for(role: Role) -> list[str]:
    return sorted(ROLE_PERMISSIONS.get(role, frozenset()))

