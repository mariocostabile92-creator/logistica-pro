from pydantic import BaseModel


class DriverShiftDriverSessionError(RuntimeError):
    code = "DRIVER_SHIFT_DRIVER_SESSION_ERROR"


class DriverShiftLoginInvalidError(DriverShiftDriverSessionError):
    code = "DRIVER_SHIFT_LOGIN_INVALID"


class DriverShiftLoginRateLimitedError(DriverShiftLoginInvalidError):
    code = "DRIVER_SHIFT_LOGIN_RATE_LIMITED"


class DriverShiftSessionInvalidError(DriverShiftDriverSessionError):
    code = "DRIVER_SHIFT_SESSION_INVALID"


class DriverShiftDriverView(BaseModel):
    authenticated: bool = True
    driver_name: str
    period_start: str
    period_end: str
    access_status: str


class DriverShiftLogoutView(BaseModel):
    authenticated: bool = False

