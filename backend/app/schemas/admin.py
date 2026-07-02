import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field


class CompanyCreate(BaseModel):
    name: str
    name_kana: str | None = None
    slug: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{1,62}$")
    max_users: int = 50
    max_devices: int = 10
    settings: dict = Field(default_factory=dict)


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
