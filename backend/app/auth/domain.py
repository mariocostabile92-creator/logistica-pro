from dataclasses import dataclass
from enum import StrEnum


class Role(StrEnum):
    OPERATIONS_MANAGER = "operations_manager"
    FLEET_MANAGER = "fleet_manager"
    DISPATCHER = "dispatcher"
    VIEWER = "viewer"
    ADMINISTRATOR = "administrator"


@dataclass(frozen=True)
class AuthenticatedUser:
    id: str
    email: str
    role: Role
    organization_id: str
    organization_name: str
    first_name: str = ""
    last_name: str = ""
