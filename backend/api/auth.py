from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from backend.api.dependencies import client_context, get_current_user, require_role
from backend.config import settings
from backend.db.session import get_db
from backend.models.auth import User, UserRole
from backend.schemas.auth import (
    AuthResponse,
    LoginRequest,
    MessageResponse,
    PasswordResetConfirmRequest,
    PasswordResetRequest,
    RefreshRequest,
    RegisterRequest,
    UserResponse,
    VerifyEmailConfirmRequest,
    VerifyEmailRequest,
)
from backend.services.auth_service import (
    confirm_email_verification,
    confirm_password_reset,
    login,
    logout,
    refresh_tokens,
    register_user,
    request_email_verification,
    request_password_reset,
)
from backend.services.email_service import send_email
from backend.services.rate_limiter import assert_not_rate_limited

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=UserResponse)
def register(payload: RegisterRequest, request: Request, db: Session = Depends(get_db)):
    ip_address, user_agent = client_context(request)
    assert_not_rate_limited(f"register:{ip_address}:{payload.email.lower()}")
    user = register_user(db, payload.email, payload.password, ip_address, user_agent)
    db.commit()
    db.refresh(user)
    return UserResponse.model_validate(user)


@router.post("/login", response_model=AuthResponse)
def login_user(payload: LoginRequest, request: Request, db: Session = Depends(get_db)):
    ip_address, user_agent = client_context(request)
    assert_not_rate_limited(f"login:{ip_address}:{payload.email.lower()}")
    user, tokens = login(db, payload.email, payload.password, ip_address, user_agent)
    db.commit()
    db.refresh(user)
    return AuthResponse(user=UserResponse.model_validate(user), tokens=tokens)


@router.post("/refresh", response_model=AuthResponse)
def refresh(payload: RefreshRequest, request: Request, db: Session = Depends(get_db)):
    ip_address, user_agent = client_context(request)
    user, tokens = refresh_tokens(db, payload.refresh_token, ip_address, user_agent)
    db.commit()
    db.refresh(user)
    return AuthResponse(user=UserResponse.model_validate(user), tokens=tokens)


@router.post("/logout", response_model=MessageResponse)
def logout_user(payload: RefreshRequest, request: Request, db: Session = Depends(get_db)):
    ip_address, user_agent = client_context(request)
    logout(db, payload.refresh_token, ip_address, user_agent)
    db.commit()
    return MessageResponse(message="Logged out successfully")


@router.post("/verify-email/request", response_model=MessageResponse)
def verify_email_request(payload: VerifyEmailRequest, request: Request, db: Session = Depends(get_db)):
    ip_address, user_agent = client_context(request)
    token = request_email_verification(db, payload.email, ip_address, user_agent)
    db.commit()
    if token:
        verification_url = f"{settings.FRONTEND_BASE_URL}/verify-email?token={token}"
        send_email(
            payload.email,
            "Verify your email",
            f"Open this link to verify your account:\n{verification_url}",
        )
    return MessageResponse(message="If the account exists, a verification link has been generated")


@router.post("/verify-email/confirm", response_model=MessageResponse)
def verify_email_confirm(payload: VerifyEmailConfirmRequest, request: Request, db: Session = Depends(get_db)):
    ip_address, user_agent = client_context(request)
    confirm_email_verification(db, payload.token, ip_address, user_agent)
    db.commit()
    return MessageResponse(message="Email verified successfully")


@router.post("/password-reset/request", response_model=MessageResponse)
def password_reset_request(payload: PasswordResetRequest, request: Request, db: Session = Depends(get_db)):
    ip_address, user_agent = client_context(request)
    token = request_password_reset(db, payload.email, ip_address, user_agent)
    db.commit()
    if token:
        reset_url = f"{settings.FRONTEND_BASE_URL}/reset-password?token={token}"
        send_email(
            payload.email,
            "Reset your password",
            f"Open this link to reset your password:\n{reset_url}",
        )
    return MessageResponse(message="If the account exists, a reset link has been generated")


@router.post("/password-reset/confirm", response_model=MessageResponse)
def password_reset_confirm(payload: PasswordResetConfirmRequest, request: Request, db: Session = Depends(get_db)):
    ip_address, user_agent = client_context(request)
    confirm_password_reset(db, payload.token, payload.new_password, ip_address, user_agent)
    db.commit()
    return MessageResponse(message="Password reset successful")


@router.get("/me", response_model=UserResponse)
def get_me(user: User = Depends(get_current_user)):
    return UserResponse.model_validate(user)


@router.get("/admin-only", response_model=MessageResponse)
def admin_only(_: User = Depends(require_role(UserRole.admin))):
    return MessageResponse(message="Admin access granted")
