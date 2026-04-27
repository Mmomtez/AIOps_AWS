from __future__ import annotations

from datetime import timedelta
from uuid import UUID, uuid4

from fastapi import HTTPException, status
from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from backend.config import settings
from backend.models.auth import (
    AuditEventType,
    AuthAuditEvent,
    EmailVerificationToken,
    PasswordResetToken,
    RefreshToken,
    User,
    UserRole,
)
from backend.schemas.auth import AuthTokens
from backend.services.security import (
    create_access_token,
    create_refresh_token,
    decode_refresh_token,
    generate_opaque_token,
    hash_password,
    hash_token,
    utcnow,
    verify_password,
)


def _audit(
    db: Session,
    event_type: AuditEventType,
    user_id: UUID | None,
    ip_address: str | None,
    user_agent: str | None,
    detail: str | None = None,
    event_metadata: dict | None = None,
) -> None:
    db.add(
        AuthAuditEvent(
            event_type=event_type,
            user_id=user_id,
            ip_address=ip_address,
            user_agent=user_agent,
            detail=detail,
            event_metadata=event_metadata,
        )
    )


def _issue_tokens(db: Session, user: User, ip_address: str | None, user_agent: str | None) -> AuthTokens:
    now = utcnow()
    access_expires_at = now + settings.ACCESS_TOKEN_EXPIRES
    refresh_expires_at = now + settings.REFRESH_TOKEN_EXPIRES
    refresh_jti = str(uuid4())

    access_token = create_access_token(str(user.id), user.role.value, access_expires_at)
    refresh_token = create_refresh_token(str(user.id), refresh_jti, refresh_expires_at)

    db.add(
        RefreshToken(
            user_id=user.id,
            jti=refresh_jti,
            token_hash=hash_token(refresh_token),
            expires_at=refresh_expires_at,
            ip_address=ip_address,
            user_agent=user_agent,
        )
    )

    return AuthTokens(
        access_token=access_token,
        refresh_token=refresh_token,
        access_expires_in_seconds=int(settings.ACCESS_TOKEN_EXPIRES.total_seconds()),
        refresh_expires_in_seconds=int(settings.REFRESH_TOKEN_EXPIRES.total_seconds()),
    )


def register_user(db: Session, email: str, password: str, ip_address: str | None, user_agent: str | None) -> User:
    user_exists = db.execute(select(User).where(User.email == email.lower())).scalar_one_or_none()
    if user_exists:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")

    user = User(email=email.lower(), password_hash=hash_password(password), role=UserRole.user)
    db.add(user)
    db.flush()

    _audit(db, AuditEventType.register, user.id, ip_address, user_agent, detail="User registered")
    return user


def authenticate_user(db: Session, email: str, password: str, ip_address: str | None, user_agent: str | None) -> User:
    user = db.execute(select(User).where(User.email == email.lower())).scalar_one_or_none()
    if not user:
        _audit(db, AuditEventType.login_failure, None, ip_address, user_agent, detail="Unknown user login attempt")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    now = utcnow()
    if user.locked_until and user.locked_until > now:
        _audit(db, AuditEventType.login_failure, user.id, ip_address, user_agent, detail="Account locked")
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Account temporarily locked")

    if not verify_password(password, user.password_hash):
        user.failed_attempts += 1
        detail = "Invalid password"
        if user.failed_attempts >= settings.LOCKOUT_THRESHOLD:
            user.locked_until = now + timedelta(minutes=settings.LOCKOUT_MINUTES)
            user.failed_attempts = 0
            detail = "Account locked due to failed attempts"
        _audit(db, AuditEventType.login_failure, user.id, ip_address, user_agent, detail=detail)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    user.failed_attempts = 0
    user.locked_until = None
    _audit(db, AuditEventType.login_success, user.id, ip_address, user_agent, detail="Login successful")
    return user


def login(db: Session, email: str, password: str, ip_address: str | None, user_agent: str | None) -> tuple[User, AuthTokens]:
    user = authenticate_user(db, email, password, ip_address, user_agent)
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User account is inactive")

    tokens = _issue_tokens(db, user, ip_address, user_agent)
    return user, tokens


def refresh_tokens(db: Session, refresh_token: str, ip_address: str | None, user_agent: str | None) -> tuple[User, AuthTokens]:
    try:
        payload = decode_refresh_token(refresh_token)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token") from exc

    if payload.get("type") != "refresh":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token type")

    jti = payload.get("jti")
    user_id = payload.get("sub")
    token_hash = hash_token(refresh_token)
    now = utcnow()

    stored_token = db.execute(
        select(RefreshToken).where(
            and_(
                RefreshToken.jti == jti,
                RefreshToken.token_hash == token_hash,
                RefreshToken.revoked_at.is_(None),
                RefreshToken.expires_at > now,
            )
        )
    ).scalar_one_or_none()
    if not stored_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh token revoked or expired")

    user = db.execute(select(User).where(User.id == UUID(user_id))).scalar_one_or_none()
    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid user")

    stored_token.revoked_at = now
    tokens = _issue_tokens(db, user, ip_address, user_agent)
    _audit(db, AuditEventType.token_refresh, user.id, ip_address, user_agent, detail="Refresh token rotated")
    return user, tokens


def logout(db: Session, refresh_token: str, ip_address: str | None, user_agent: str | None) -> None:
    try:
        payload = decode_refresh_token(refresh_token)
    except Exception:
        return

    jti = payload.get("jti")
    stored_token = db.execute(
        select(RefreshToken).where(
            and_(RefreshToken.jti == jti, RefreshToken.revoked_at.is_(None)),
        )
    ).scalar_one_or_none()
    if stored_token:
        stored_token.revoked_at = utcnow()
        _audit(db, AuditEventType.logout, stored_token.user_id, ip_address, user_agent, detail="User logout")


def request_email_verification(db: Session, email: str, ip_address: str | None, user_agent: str | None) -> str | None:
    user = db.execute(select(User).where(User.email == email.lower())).scalar_one_or_none()
    if not user:
        return None

    raw_token = generate_opaque_token()
    expires_at = utcnow() + timedelta(hours=settings.EMAIL_TOKEN_EXPIRE_HOURS)
    db.add(
        EmailVerificationToken(
            user_id=user.id,
            token_hash=hash_token(raw_token),
            expires_at=expires_at,
        )
    )
    db.flush()
    _audit(db, AuditEventType.verify_email_request, user.id, ip_address, user_agent, detail="Email verification requested")
    return raw_token


def confirm_email_verification(db: Session, token: str, ip_address: str | None, user_agent: str | None) -> None:
    now = utcnow()
    token_hash = hash_token(token)
    verification = db.execute(
        select(EmailVerificationToken).where(
            and_(
                EmailVerificationToken.token_hash == token_hash,
                EmailVerificationToken.used_at.is_(None),
                EmailVerificationToken.expires_at > now,
            )
        )
    ).scalar_one_or_none()
    if not verification:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or expired token")

    user = db.execute(select(User).where(User.id == verification.user_id)).scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid token")

    verification.used_at = now
    user.is_verified = True
    _audit(db, AuditEventType.verify_email_success, user.id, ip_address, user_agent, detail="Email verified")


def request_password_reset(db: Session, email: str, ip_address: str | None, user_agent: str | None) -> str | None:
    user = db.execute(select(User).where(User.email == email.lower())).scalar_one_or_none()
    if not user:
        return None

    raw_token = generate_opaque_token()
    expires_at = utcnow() + timedelta(minutes=settings.PASSWORD_RESET_EXPIRE_MINUTES)
    db.add(
        PasswordResetToken(
            user_id=user.id,
            token_hash=hash_token(raw_token),
            expires_at=expires_at,
        )
    )
    db.flush()
    _audit(db, AuditEventType.password_reset_request, user.id, ip_address, user_agent, detail="Password reset requested")
    return raw_token


def confirm_password_reset(
    db: Session, token: str, new_password: str, ip_address: str | None, user_agent: str | None
) -> None:
    now = utcnow()
    token_hash = hash_token(token)
    reset = db.execute(
        select(PasswordResetToken).where(
            and_(
                PasswordResetToken.token_hash == token_hash,
                PasswordResetToken.used_at.is_(None),
                PasswordResetToken.expires_at > now,
            )
        )
    ).scalar_one_or_none()
    if not reset:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or expired token")

    user = db.execute(select(User).where(User.id == reset.user_id)).scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid token")

    user.password_hash = hash_password(new_password)
    reset.used_at = now
    _audit(db, AuditEventType.password_reset_success, user.id, ip_address, user_agent, detail="Password reset successful")
