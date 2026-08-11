from pydantic import BaseModel, Field


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


class DriverShiftPublicShift(BaseModel):
    raw_shift_code: str | None = None
    display_label: str
    start_time: str | None = None
    end_time: str | None = None
    status: str | None = None
    availability: bool | None = None
    station: str | None = None


class DriverShiftPublicDay(BaseModel):
    operational_date: str
    weekday_label: str
    date_label: str
    missing: bool = False
    shifts: list[DriverShiftPublicShift] = Field(default_factory=list)


class DriverShiftPublicWeek(BaseModel):
    driver_name: str
    period_start: str
    period_end: str
    days: list[DriverShiftPublicDay] = Field(default_factory=list)
    acknowledged: bool = False
    acknowledged_at: str | None = None
