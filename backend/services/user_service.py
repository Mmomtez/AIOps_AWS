from __future__ import annotations

from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from backend.models.auth import AuditEventType, AuthAuditEvent, RefreshToken, User, UserRole
from backend.schemas.users import AdminUserUpdateRequest, UserUpdateMeRequest
from backend.services.auth_service import _audit
from backend.services.security import decode_refresh_token, hash_token, utcnow, verify_password
from backend.services.security import hash_password as hash_new_password


def _get_active_refresh_tokens(db: Session, user_id: UUID) -> list[RefreshToken]:
    now = utcnow()
    return list(
        db.execute(
            select(RefreshToken).where(
                and_(
                    RefreshToken.user_id == user_id,
                    RefreshToken.revoked_at.is_(None),
                    RefreshToken.expires_at > now,
                )
            ).order_by(RefreshToken.created_at.desc())
        ).scalars().all()
    )


def _revoke_refresh_tokens(
    db: Session,
    user_id: UUID,
    *,
    except_jti: str | None = None,
    actor_user_id: UUID | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
    audit_type: AuditEventType = AuditEventType.session_revoked,
    detail: str = "Sessions revoked",
) -> int:
    now = utcnow()
    tokens = _get_active_refresh_tokens(db, user_id)
    revoked_count = 0
    for token in tokens:
        if except_jti and token.jti == except_jti:
            continue
        token.revoked_at = now
        revoked_count += 1

    if revoked_count:
        _audit(
            db,
            audit_type,
            actor_user_id or user_id,
            ip_address,
            user_agent,
            detail=detail,
            event_metadata={"target_user_id": str(user_id), "revoked_count": revoked_count},
        )
    return revoked_count


def _count_admins(db: Session) -> int:
    return db.execute(
        select(func.count()).select_from(User).where(and_(User.role == UserRole.admin, User.is_active.is_(True)))
    ).scalar_one()


def update_profile(
    db: Session,
    user: User,
    payload: UserUpdateMeRequest,
    ip_address: str | None,
    user_agent: str | None,
) -> User:
    if payload.display_name is not None:
        user.display_name = payload.display_name.strip() if payload.display_name else None

    _audit(db, AuditEventType.profile_updated, user.id, ip_address, user_agent, detail="Profile updated")
    return user


def change_password(
    db: Session,
    user: User,
    current_password: str,
    new_password: str,
    ip_address: str | None,
    user_agent: str | None,
) -> None:
    if not verify_password(current_password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Current password is incorrect")

    if current_password == new_password:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="New password must differ from current password")

    user.password_hash = hash_new_password(new_password)
    user.password_changed_at = utcnow()
    _revoke_refresh_tokens(
        db,
        user.id,
        ip_address=ip_address,
        user_agent=user_agent,
        audit_type=AuditEventType.session_revoked,
        detail="Sessions revoked after password change",
    )
    _audit(db, AuditEventType.password_changed, user.id, ip_address, user_agent, detail="Password changed")


def deactivate_account(
    db: Session,
    user: User,
    ip_address: str | None,
    user_agent: str | None,
) -> None:
    if not user.is_active:
        return

    now = utcnow()
    user.is_active = False
    user.deactivated_at = now
    _revoke_refresh_tokens(
        db,
        user.id,
        ip_address=ip_address,
        user_agent=user_agent,
        audit_type=AuditEventType.account_deactivated,
        detail="Account deactivated",
    )
    _audit(db, AuditEventType.account_deactivated, user.id, ip_address, user_agent, detail="Account deactivated")


def list_sessions(
    db: Session, user: User, current_refresh_token: str | None = None
) -> tuple[list[tuple[RefreshToken, bool]], int]:
    tokens = _get_active_refresh_tokens(db, user.id)
    current_jti: str | None = None
    if current_refresh_token:
        try:
            payload = decode_refresh_token(current_refresh_token)
            current_jti = payload.get("jti")
        except Exception:
            current_jti = None

    return [(token, token.jti == current_jti) for token in tokens], len(tokens)


def revoke_session(
    db: Session,
    user: User,
    session_id: UUID,
    ip_address: str | None,
    user_agent: str | None,
) -> None:
    now = utcnow()
    token = db.execute(
        select(RefreshToken).where(
            and_(
                RefreshToken.id == session_id,
                RefreshToken.user_id == user.id,
                RefreshToken.revoked_at.is_(None),
                RefreshToken.expires_at > now,
            )
        )
    ).scalar_one_or_none()
    if not token:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

    token.revoked_at = now
    _audit(
        db,
        AuditEventType.session_revoked,
        user.id,
        ip_address,
        user_agent,
        detail="Session revoked",
        event_metadata={"session_id": str(session_id)},
    )


def revoke_all_sessions(
    db: Session,
    user: User,
    keep_refresh_token: str | None,
    ip_address: str | None,
    user_agent: str | None,
) -> int:
    except_jti: str | None = None
    if keep_refresh_token:
        try:
            payload = decode_refresh_token(keep_refresh_token)
            if payload.get("type") != "refresh":
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid refresh token")
            except_jti = payload.get("jti")
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid refresh token") from exc

    return _revoke_refresh_tokens(
        db,
        user.id,
        except_jti=except_jti,
        ip_address=ip_address,
        user_agent=user_agent,
        detail="All sessions revoked except current" if except_jti else "All sessions revoked",
    )


def get_user_activity(db: Session, user: User, *, limit: int = 20) -> tuple[list[AuthAuditEvent], int]:
    limit = min(max(limit, 1), 100)
    query = (
        select(AuthAuditEvent)
        .where(AuthAuditEvent.user_id == user.id)
        .order_by(AuthAuditEvent.created_at.desc())
        .limit(limit)
    )
    items = list(db.execute(query).scalars().all())
    total = db.execute(
        select(func.count()).select_from(AuthAuditEvent).where(AuthAuditEvent.user_id == user.id)
    ).scalar_one()
    return items, total


def list_users(
    db: Session,
    *,
    page: int = 1,
    page_size: int = 20,
    search: str | None = None,
    role: UserRole | None = None,
    is_active: bool | None = None,
) -> tuple[list[User], int]:
    page = max(page, 1)
    page_size = min(max(page_size, 1), 100)

    filters = []
    if search:
        term = f"%{search.strip().lower()}%"
        filters.append(or_(func.lower(User.email).like(term), func.lower(User.display_name).like(term)))
    if role is not None:
        filters.append(User.role == role)
    if is_active is not None:
        filters.append(User.is_active.is_(is_active))

    base_query = select(User)
    count_query = select(func.count()).select_from(User)
    if filters:
        base_query = base_query.where(and_(*filters))
        count_query = count_query.where(and_(*filters))

    total = db.execute(count_query).scalar_one()
    users = list(
        db.execute(
            base_query.order_by(User.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
        ).scalars().all()
    )
    return users, total


def get_user_by_id(db: Session, user_id: UUID) -> User:
    user = db.execute(select(User).where(User.id == user_id)).scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return user


def admin_update_user(
    db: Session,
    actor: User,
    target: User,
    payload: AdminUserUpdateRequest,
    ip_address: str | None,
    user_agent: str | None,
) -> User:
    if actor.id == target.id and payload.is_active is False:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="You cannot deactivate your own account")

    if payload.role is not None and payload.role != target.role:
        if target.role == UserRole.admin and payload.role != UserRole.admin and _count_admins(db) <= 1:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot demote the last active admin")
        target.role = payload.role

    if payload.is_active is not None and payload.is_active != target.is_active:
        if not payload.is_active and target.role == UserRole.admin and _count_admins(db) <= 1:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot deactivate the last active admin")
        target.is_active = payload.is_active
        if payload.is_active:
            target.deactivated_at = None
        else:
            target.deactivated_at = utcnow()
            _revoke_refresh_tokens(
                db,
                target.id,
                actor_user_id=actor.id,
                ip_address=ip_address,
                user_agent=user_agent,
                audit_type=AuditEventType.admin_sessions_revoked,
                detail="Sessions revoked due to deactivation",
            )

    if payload.is_verified is not None:
        target.is_verified = payload.is_verified

    if payload.display_name is not None:
        target.display_name = payload.display_name.strip() if payload.display_name else None

    _audit(
        db,
        AuditEventType.admin_user_updated,
        actor.id,
        ip_address,
        user_agent,
        detail="Admin updated user",
        event_metadata={"target_user_id": str(target.id), "changes": payload.model_dump(exclude_unset=True)},
    )
    return target


def admin_unlock_user(
    db: Session,
    actor: User,
    target: User,
    ip_address: str | None,
    user_agent: str | None,
) -> User:
    target.failed_attempts = 0
    target.locked_until = None
    _audit(
        db,
        AuditEventType.admin_user_unlocked,
        actor.id,
        ip_address,
        user_agent,
        detail="Admin unlocked user account",
        event_metadata={"target_user_id": str(target.id)},
    )
    return target


def admin_revoke_sessions(
    db: Session,
    actor: User,
    target: User,
    ip_address: str | None,
    user_agent: str | None,
) -> int:
    revoked = _revoke_refresh_tokens(
        db,
        target.id,
        actor_user_id=actor.id,
        ip_address=ip_address,
        user_agent=user_agent,
        audit_type=AuditEventType.admin_sessions_revoked,
        detail="Admin revoked user sessions",
    )
    return revoked
