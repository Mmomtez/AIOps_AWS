from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from backend.api.dependencies import client_context, get_current_user, require_role
from backend.db.session import get_db
from backend.models.auth import User, UserRole
from backend.schemas.auth import MessageResponse, UserResponse
from backend.schemas.users import (
    ActivityEventResponse,
    ActivityListResponse,
    AdminUserUpdateRequest,
    ChangePasswordRequest,
    RevokeAllSessionsRequest,
    SessionListResponse,
    SessionResponse,
    UserListResponse,
    UserUpdateMeRequest,
)
from backend.services.rate_limiter import assert_not_rate_limited
from backend.services.user_service import (
    admin_revoke_sessions,
    admin_unlock_user,
    admin_update_user,
    change_password,
    deactivate_account,
    get_user_activity,
    get_user_by_id,
    list_sessions,
    list_users,
    revoke_all_sessions,
    revoke_session,
    update_profile,
)

router = APIRouter(prefix="/auth", tags=["auth"])


@router.patch("/me", response_model=UserResponse)
def patch_me(
    payload: UserUpdateMeRequest,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    ip_address, user_agent = client_context(request)
    update_profile(db, user, payload, ip_address, user_agent)
    db.commit()
    db.refresh(user)
    return UserResponse.model_validate(user)


@router.post("/me/change-password", response_model=MessageResponse)
def change_password_me(
    payload: ChangePasswordRequest,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    ip_address, user_agent = client_context(request)
    assert_not_rate_limited(f"change-password:{ip_address}:{user.email.lower()}")
    change_password(db, user, payload.current_password, payload.new_password, ip_address, user_agent)
    db.commit()
    return MessageResponse(message="Password changed successfully. Please sign in again.")


@router.post("/me/deactivate", response_model=MessageResponse)
def deactivate_me(
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    ip_address, user_agent = client_context(request)
    deactivate_account(db, user, ip_address, user_agent)
    db.commit()
    return MessageResponse(message="Account deactivated successfully")


@router.get("/me/sessions", response_model=SessionListResponse)
def get_my_sessions(
    refresh_token: str | None = Query(default=None),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    tokens, total = list_sessions(db, user, refresh_token)
    return SessionListResponse(
        items=[
            SessionResponse(
                id=token.id,
                created_at=token.created_at,
                expires_at=token.expires_at,
                ip_address=token.ip_address,
                user_agent=token.user_agent,
                is_current=is_current,
            )
            for token, is_current in tokens
        ],
        total=total,
    )


@router.delete("/me/sessions/{session_id}", response_model=MessageResponse)
def delete_my_session(
    session_id: UUID,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    ip_address, user_agent = client_context(request)
    revoke_session(db, user, session_id, ip_address, user_agent)
    db.commit()
    return MessageResponse(message="Session revoked successfully")


@router.post("/me/sessions/revoke-all", response_model=MessageResponse)
def revoke_all_my_sessions(
    payload: RevokeAllSessionsRequest,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    ip_address, user_agent = client_context(request)
    revoked = revoke_all_sessions(db, user, payload.keep_refresh_token, ip_address, user_agent)
    db.commit()
    return MessageResponse(message=f"Revoked {revoked} session(s)")


@router.get("/me/activity", response_model=ActivityListResponse)
def get_my_activity(
    limit: int = Query(default=20, ge=1, le=100),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    events, total = get_user_activity(db, user, limit=limit)
    return ActivityListResponse(
        items=[ActivityEventResponse.model_validate(event) for event in events],
        total=total,
    )
