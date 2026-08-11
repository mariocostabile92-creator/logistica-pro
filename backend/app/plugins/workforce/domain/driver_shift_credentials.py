from enum import StrEnum

from pydantic import BaseModel, Field

from app.plugins.workforce.domain.driver_shift_distribution import (
    DriverShiftDistributionError,
    DriverShiftDistributionNotFoundError,
)


class DriverShiftCredentialStatus(StrEnum):
    ACTIVE = "ACTIVE"
    RESET_REQUIRED = "RESET_REQUIRED"
    REVOKED = "REVOKED"


class DriverShiftCredentialError(DriverShiftDistributionError):
    code = "DRIVER_SHIFT_CREDENTIAL_INVALID"


class DriverShiftCredentialNotFoundError(DriverShiftDistributionNotFoundError):
    code = "DRIVER_SHIFT_CREDENTIAL_NOT_FOUND"


class DriverShiftCredentialRecipient(BaseModel):
    workforce_member_id: int
    display_name: str
    credential_status: DriverShiftCredentialStatus | None = None


class DriverShiftCredentialSummary(BaseModel):
    recipients_total: int = Field(ge=0)
    credentials_ready: int = Field(ge=0)
    already_existing: int = Field(ge=0)
    newly_created: int = Field(ge=0)
    revoked: int = Field(ge=0)
    reset_required: int = Field(ge=0)
    missing: int = Field(ge=0)
    errors: int = Field(ge=0)


class DriverShiftCredentialReadModel(BaseModel):
    distribution_id: int
    summary: DriverShiftCredentialSummary
    recipients: list[DriverShiftCredentialRecipient] = Field(default_factory=list)


class DriverShiftInitialCredential(BaseModel):
    display_name: str
    access_code: str
    initial_pin: str


class DriverShiftCredentialPrepareResult(DriverShiftCredentialReadModel):
    initial_credentials: list[DriverShiftInitialCredential] = Field(default_factory=list)


class DriverShiftCredentialResetResult(BaseModel):
    workforce_member_id: int
    display_name: str
    credential_status: DriverShiftCredentialStatus
    generation: int = Field(ge=1)
    initial_pin: str


class DriverShiftCredentialMutationResult(BaseModel):
    workforce_member_id: int
    display_name: str
    credential_status: DriverShiftCredentialStatus
    generation: int = Field(ge=1)
