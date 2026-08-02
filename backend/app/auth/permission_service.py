from app.auth.domain import Role


ROLE_PERMISSIONS: dict[Role, frozenset[str]] = {
    Role.ADMINISTRATOR: frozenset({"admin:read", "admin:write", "users:manage", "planning:read", "planning:write", "fleet:read", "fleet:write", "documents:read", "documents:write", "documents:archive", "attachments:read", "attachments:write", "journal:read", "journal:write", "journal:media", "journal:media:delete", "journal:archive", "journal:configure", "workforce:read", "workforce:write", "workforce:policy:write", "workforce:override"}),
    Role.OPERATIONS_MANAGER: frozenset({"admin:read", "admin:write", "planning:read", "planning:write", "fleet:read", "fleet:write", "documents:read", "documents:write", "documents:archive", "attachments:read", "attachments:write", "journal:read", "journal:write", "journal:media", "journal:media:delete", "journal:archive", "workforce:read", "workforce:write", "workforce:override"}),
    Role.FLEET_MANAGER: frozenset({"admin:read", "admin:write", "planning:read", "fleet:read", "fleet:write", "documents:read", "documents:write", "documents:archive", "attachments:read", "attachments:write", "journal:read", "journal:write", "journal:media", "journal:media:delete", "journal:archive", "workforce:read"}),
    Role.DISPATCHER: frozenset({"admin:read", "admin:write", "planning:read", "planning:write", "fleet:read", "documents:read", "attachments:read", "journal:read", "workforce:read", "workforce:write", "workforce:override"}),
    Role.VIEWER: frozenset({"admin:read", "planning:read", "fleet:read", "documents:read", "attachments:read", "journal:read", "journal:archive", "workforce:read"}),
}


def has_permission(role: Role, permission: str) -> bool:
    return permission in ROLE_PERMISSIONS.get(role, frozenset())


def permissions_for(role: Role) -> list[str]:
    return sorted(ROLE_PERMISSIONS.get(role, frozenset()))
