from enum import StrEnum

from pydantic import BaseModel

from app.plugins.workforce.domain.driver_shift_distribution import (
    DriverShiftDistributionError,
    DriverShiftDistributionNotFoundError,
)


class DriverShiftPortalStatus(StrEnum):
    ACTIVE = "ACTIVE"
    REVOKED = "REVOKED"
    EXPIRED = "EXPIRED"


class DriverShiftPortalNotFoundError(DriverShiftDistributionNotFoundError):
    code = "DRIVER_SHIFT_PORTAL_NOT_FOUND"


class DriverShiftPortalInvalidError(DriverShiftDistributionError):
    code = "DRIVER_SHIFT_PORTAL_INVALID"


class DriverShiftPortalAccess(BaseModel):
    id: int
    distribution_id: int
    status: DriverShiftPortalStatus
    access_url: str | None = None
    expires_at: str
    created_at: str
    created_by: str
    revoked_at: str | None = None


class DriverShiftPortalAvailability(BaseModel):
    available: bool = True
