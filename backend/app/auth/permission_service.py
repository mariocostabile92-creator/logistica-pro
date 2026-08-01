from app.auth.domain import Role


ROLE_PERMISSIONS: dict[Role, frozenset[str]] = {
    Role.ADMINISTRATOR: frozenset({"admin:read", "admin:write", "users:manage", "documents:read", "documents:write", "documents:archive", "attachments:write", "journal:read", "journal:write", "journal:media", "journal:media:delete", "journal:archive", "journal:configure"}),
    Role.OPERATIONS_MANAGER: frozenset({"admin:read", "admin:write", "documents:read", "documents:write", "documents:archive", "attachments:write", "journal:read", "journal:write", "journal:media", "journal:media:delete", "journal:archive"}),
    Role.FLEET_MANAGER: frozenset({"admin:read", "admin:write", "documents:read", "documents:write", "documents:archive", "attachments:write", "journal:read", "journal:write", "journal:media", "journal:media:delete", "journal:archive"}),
    Role.DISPATCHER: frozenset({"admin:read", "admin:write", "documents:read", "journal:read"}),
    Role.VIEWER: frozenset({"admin:read", "documents:read", "journal:read", "journal:archive"}),
}


def has_permission(role: Role, permission: str) -> bool:
    return permission in ROLE_PERMISSIONS.get(role, frozenset())


def permissions_for(role: Role) -> list[str]:
    return sorted(ROLE_PERMISSIONS.get(role, frozenset()))
