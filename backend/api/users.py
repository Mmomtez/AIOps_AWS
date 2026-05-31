from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from backend.api.dependencies import client_context, require_role
from backend.db.session import get_db
from backend.models.auth import User, UserRole
from backend.schemas.auth import MessageResponse, UserResponse
from backend.schemas.users import AdminUserUpdateRequest, UserListResponse
from backend.services.user_service import (
    admin_revoke_sessions,
    admin_unlock_user,
    admin_update_user,
    get_user_by_id,
    list_users,
)

router = APIRouter(prefix="/users", tags=["users"])


@router.get("", response_model=UserListResponse)
def get_users(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    search: str | None = Query(default=None),
    role: UserRole | None = Query(default=None),
    is_active: bool | None = Query(default=None),
    _: User = Depends(require_role(UserRole.admin)),
    db: Session = Depends(get_db),
):
    users, total = list_users(db, page=page, page_size=page_size, search=search, role=role, is_active=is_active)
    return UserListResponse(
        items=[UserResponse.model_validate(user) for user in users],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/{user_id}", response_model=UserResponse)
def get_user(
    user_id: UUID,
    _: User = Depends(require_role(UserRole.admin)),
    db: Session = Depends(get_db),
):
    user = get_user_by_id(db, user_id)
    return UserResponse.model_validate(user)


@router.patch("/{user_id}", response_model=UserResponse)
def patch_user(
    user_id: UUID,
    payload: AdminUserUpdateRequest,
    request: Request,
    actor: User = Depends(require_role(UserRole.admin)),
    db: Session = Depends(get_db),
):
    ip_address, user_agent = client_context(request)
    target = get_user_by_id(db, user_id)
    admin_update_user(db, actor, target, payload, ip_address, user_agent)
    db.commit()
    db.refresh(target)
    return UserResponse.model_validate(target)


@router.post("/{user_id}/unlock", response_model=UserResponse)
def unlock_user(
    user_id: UUID,
    request: Request,
    actor: User = Depends(require_role(UserRole.admin)),
    db: Session = Depends(get_db),
):
    ip_address, user_agent = client_context(request)
    target = get_user_by_id(db, user_id)
    admin_unlock_user(db, actor, target, ip_address, user_agent)
    db.commit()
    db.refresh(target)
    return UserResponse.model_validate(target)


@router.post("/{user_id}/revoke-sessions", response_model=MessageResponse)
def revoke_user_sessions(
    user_id: UUID,
    request: Request,
    actor: User = Depends(require_role(UserRole.admin)),
    db: Session = Depends(get_db),
):
    ip_address, user_agent = client_context(request)
    target = get_user_by_id(db, user_id)
    revoked = admin_revoke_sessions(db, actor, target, ip_address, user_agent)
    db.commit()
    return MessageResponse(message=f"Revoked {revoked} session(s)")


@router.delete("/{user_id}", response_model=UserResponse)
def deactivate_user(
    user_id: UUID,
    request: Request,
    actor: User = Depends(require_role(UserRole.admin)),
    db: Session = Depends(get_db),
):
    ip_address, user_agent = client_context(request)
    target = get_user_by_id(db, user_id)
    admin_update_user(
        db,
        actor,
        target,
        AdminUserUpdateRequest(is_active=False),
        ip_address,
        user_agent,
    )
    db.commit()
    db.refresh(target)
    return UserResponse.model_validate(target)
