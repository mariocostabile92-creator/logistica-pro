from pydantic import BaseModel, Field, field_validator, model_validator

from app.auth.domain import Role


class EmailModel(BaseModel):
    email: str = Field(min_length=3, max_length=320)

    @field_validator("email")
    @classmethod
    def valid_email(cls, value: str) -> str:
        normalized = value.strip().casefold()
        if "@" not in normalized or normalized.startswith("@") or normalized.endswith("@"):
            raise ValueError("Email non valida.")
        return normalized


class LoginRequest(EmailModel):
    password: str = Field(min_length=1, max_length=256)
    remember_me: bool = False


class BootstrapOrganization(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    primary_station: str | None = Field(default=None, max_length=160)
    timezone: str = Field(default="Europe/Rome", min_length=2, max_length=80)
    language: str = Field(default="it", min_length=2, max_length=10)


class BootstrapAdministrator(EmailModel):
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=10, max_length=256)
    password_confirmation: str = Field(min_length=10, max_length=256)

    @model_validator(mode="after")
    def passwords_match(self):
        if self.password != self.password_confirmation:
            raise ValueError("Le password non coincidono.")
        return self


class BootstrapRequest(BaseModel):
    organization: BootstrapOrganization
    administrator: BootstrapAdministrator


class UserCreateRequest(EmailModel):
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)
    role: Role
    temporary_password: str = Field(min_length=10, max_length=256)
    active: bool = True


class UserUpdateRequest(BaseModel):
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)
    role: Role
    active: bool


class PasswordChangeRequest(BaseModel):
    password: str = Field(min_length=10, max_length=256)
