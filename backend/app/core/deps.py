from __future__ import annotations

from typing import Optional

from fastapi import Depends, Header, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db
from app.core.security import decode_token
from app.models import User


def _extract_access_token(
    request: Request,
    authorization: Optional[str] = Header(default=None),
) -> Optional[str]:
    settings = get_settings()
    access_cookie = request.cookies.get(settings.access_cookie_name)
    if access_cookie:
        return access_cookie
    if authorization and authorization.lower().startswith('bearer '):
        return authorization[7:].strip()
    return None


def get_current_user(
    token: Optional[str] = Depends(_extract_access_token),
    db: Session = Depends(get_db),
) -> User:
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='Not authenticated')
    try:
        payload = decode_token(token)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='Invalid token') from exc
    if payload.get('typ') != 'access':
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='Invalid token type')
    user = db.scalar(select(User).where(User.id == payload.get('sub')))
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='User unavailable')
    return user


def require_admin(current_user: User = Depends(get_current_user)) -> User:
    if current_user.role != 'admin':
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail='Admin role required')
    return current_user
