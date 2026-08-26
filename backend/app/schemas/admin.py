import re
import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field, field_validator


def normalize_company_slug(value: str) -> str:
    slug = value.strip().lower().replace("_", "-")
    slug = re.sub(r"[^a-z0-9-]+", "-", slug)
    slug = re.sub(r"-{2,}", "-", slug).strip("-")
    return slug


class CompanyCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    name_kana: str | None = None
    slug: str = Field(min_length=2, max_length=63)
    max_users: int = 50
    max_devices: int = 10
    settings: dict = Field(default_factory=dict)

    @field_validator("slug", mode="before")
    @classmethod
    def _normalize_slug(cls, value: object) -> object:
        if not isinstance(value, str):
            return value
        return normalize_company_slug(value)

    @field_validator("slug")
    @classmethod
    def _slug_shape(cls, value: str) -> str:
        if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,62}", value):
            raise ValueError("Slug must be lowercase letters, numbers, and hyphens")
        return value


class CompanyUpdate(BaseModel):
    name: str | None = None
    name_kana: str | None = None
    status: str | None = None
    max_users: int | None = None
    max_devices: int | None = None
    settings: dict | None = None


class CompanyOut(BaseModel):
    id: uuid.UUID
    name: str
    name_kana: str | None
    slug: str
    status: str
    max_users: int
    max_devices: int
    settings: dict
    created_at: datetime
    admin_count: int = 0

    model_config = {"from_attributes": True}


class UserCreate(BaseModel):
    email: EmailStr
    display_name: str
    password: str = Field(min_length=8)
    role: str = "user"  # company admins may create: user | company_admin


class UserUpdate(BaseModel):
    display_name: str | None = None
    role: str | None = None
    status: str | None = None


class UserOut(BaseModel):
    id: uuid.UUID
    email: str
    display_name: str
    role: str
    status: str
    company_id: uuid.UUID | None
    last_login_at: datetime | None
    created_at: datetime | None = None

    model_config = {"from_attributes": True}


class DeviceCreate(BaseModel):
    name: str


class DeviceOut(BaseModel):
    id: uuid.UUID
    name: str
    status: str
    last_seen_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}


class DeviceCreatedOut(DeviceOut):
    # Raw token — returned exactly once, at creation.
    token: str
