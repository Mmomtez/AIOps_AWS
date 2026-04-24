from __future__ import annotations

import hashlib
import secrets
from datetime import datetime
from typing import Any
from uuid import uuid4

import jwt
from passlib.context import CryptContext

from backend.config import settings

pwd_context = CryptContext(schemes=["argon2"], deprecated="auto")


def utcnow() -> datetime:
    return datetime.utcnow()


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain_password: str, password_hash: str) -> bool:
    return pwd_context.verify(plain_password, password_hash)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def generate_opaque_token() -> str:
    return secrets.token_urlsafe(48)


def _encode_token(payload: dict[str, Any], secret: str, expires_at: datetime) -> str:
    payload_copy = payload.copy()
    payload_copy.update(
        {
            "iss": settings.JWT_ISSUER,
            "aud": settings.JWT_AUDIENCE,
            "exp": expires_at,
            "iat": utcnow(),
        }
    )
    return jwt.encode(payload_copy, secret, algorithm=settings.JWT_ALGORITHM)


def create_access_token(user_id: str, role: str, expires_at: datetime) -> str:
    payload = {"sub": user_id, "role": role, "type": "access", "jti": str(uuid4())}
    return _encode_token(payload, settings.JWT_ACCESS_SECRET, expires_at)


def create_refresh_token(user_id: str, jti: str, expires_at: datetime) -> str:
    payload = {"sub": user_id, "type": "refresh", "jti": jti}
    return _encode_token(payload, settings.JWT_REFRESH_SECRET, expires_at)


def decode_access_token(token: str) -> dict[str, Any]:
    return jwt.decode(
        token,
        settings.JWT_ACCESS_SECRET,
        algorithms=[settings.JWT_ALGORITHM],
        audience=settings.JWT_AUDIENCE,
        issuer=settings.JWT_ISSUER,
    )


def decode_refresh_token(token: str) -> dict[str, Any]:
    return jwt.decode(
        token,
        settings.JWT_REFRESH_SECRET,
        algorithms=[settings.JWT_ALGORITHM],
        audience=settings.JWT_AUDIENCE,
        issuer=settings.JWT_ISSUER,
    )
