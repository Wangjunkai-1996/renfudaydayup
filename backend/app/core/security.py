from __future__ import annotations

from datetime import datetime, timedelta, timezone
from hashlib import sha256
from typing import Any
from uuid import uuid4

import jwt
from fastapi import Response
from passlib.context import CryptContext

from app.core.config import get_settings


pwd_context = CryptContext(schemes=['pbkdf2_sha256'], deprecated='auto')
ALGORITHM = 'HS256'


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    return pwd_context.verify(password, password_hash)


def hash_token(token: str) -> str:
    return sha256(token.encode('utf-8')).hexdigest()


def _build_token(payload: dict[str, Any], expires_delta: timedelta) -> str:
    settings = get_settings()
    now = datetime.now(timezone.utc)
    token_payload = {
        **payload,
        'iat': int(now.timestamp()),
        'exp': int((now + expires_delta).timestamp()),
        'jti': str(uuid4()),
    }
    return jwt.encode(token_payload, settings.secret_key, algorithm=ALGORITHM)


def create_access_token(user_id: str, role: str, session_id: str) -> str:
    settings = get_settings()
    return _build_token(
        {'sub': user_id, 'role': role, 'sid': session_id, 'typ': 'access'},
        timedelta(minutes=settings.access_token_expire_minutes),
    )


def create_refresh_token(user_id: str, role: str, session_id: str) -> str:
    settings = get_settings()
    return _build_token(
        {'sub': user_id, 'role': role, 'sid': session_id, 'typ': 'refresh'},
        timedelta(days=settings.refresh_token_expire_days),
    )


def decode_token(token: str) -> dict[str, Any]:
    settings = get_settings()
    return jwt.decode(token, settings.secret_key, algorithms=[ALGORITHM])


def set_auth_cookies(response: Response, access_token: str, refresh_token: str) -> None:
    settings = get_settings()
    common = {
        'httponly': True,
        'secure': settings.is_production,
        'samesite': 'lax',
        'path': '/',
    }
    response.set_cookie(
        settings.access_cookie_name,
        access_token,
        max_age=settings.access_token_expire_minutes * 60,
        **common,
    )
    response.set_cookie(
        settings.refresh_cookie_name,
        refresh_token,
        max_age=settings.refresh_token_expire_days * 24 * 60 * 60,
        **common,
    )


def clear_auth_cookies(response: Response) -> None:
    settings = get_settings()
    response.delete_cookie(settings.access_cookie_name, path='/')
    response.delete_cookie(settings.refresh_cookie_name, path='/')
