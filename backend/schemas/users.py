from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from backend.models.auth import AuditEventType, UserRole
from backend.schemas.auth import UserResponse


class UserUpdateMeRequest(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=120)


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=8, max_length=128)
    new_password: str = Field(min_length=8, max_length=128)


class RevokeAllSessionsRequest(BaseModel):
    keep_refresh_token: str | None = None


class SessionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    created_at: datetime
    expires_at: datetime
    ip_address: str | None
    user_agent: str | None
    is_current: bool = False


class SessionListResponse(BaseModel):
    items: list[SessionResponse]
    total: int


class ActivityEventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    event_type: AuditEventType
    detail: str | None
    ip_address: str | None
    created_at: datetime


class ActivityListResponse(BaseModel):
    items: list[ActivityEventResponse]
    total: int


class AdminUserUpdateRequest(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=120)
    role: UserRole | None = None
    is_active: bool | None = None
    is_verified: bool | None = None


class UserListResponse(BaseModel):
    items: list[UserResponse]
    total: int
    page: int
    page_size: int
