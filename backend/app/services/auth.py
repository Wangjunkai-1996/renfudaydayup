from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    hash_token,
    verify_password,
)
from app.models import AuditLog, NotificationSetting, PaperAccount, StrategyConfig, User, UserSession
from app.repos.user_repo import get_user_by_username


def audit(db: Session, *, user_id: Optional[str], action: str, resource_type: str, resource_id: Optional[str], detail: dict) -> None:
    db.add(
        AuditLog(
            user_id=user_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            detail_json=detail,
            created_at=datetime.now(timezone.utc),
        )
    )


def ensure_user_workspace(db: Session, user: User) -> None:
    config = db.scalar(select(StrategyConfig).where(StrategyConfig.user_id == user.id))
    if config is None:
        db.add(StrategyConfig(user_id=user.id, config_json={'risk_profile': 'balanced', 'max_stocks': 3}))

    paper = db.scalar(select(PaperAccount).where(PaperAccount.user_id == user.id))
    if paper is None:
        db.add(PaperAccount(user_id=user.id, starting_cash=800000, cash=800000, realized_pnl=0))

    notification = db.scalar(select(NotificationSetting).where(NotificationSetting.user_id == user.id))
    if notification is None:
        db.add(NotificationSetting(user_id=user.id, settings_json={'serverchan_enabled': False}))


def authenticate_user(db: Session, username: str, password: str) -> User:
    user = get_user_by_username(db, username)
    if user is None or not verify_password(password, user.password_hash) or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='Invalid credentials')
    ensure_user_workspace(db, user)
    user.last_login_at = datetime.now(timezone.utc)
    db.flush()
    return user


def create_session_tokens(db: Session, user: User, *, user_agent: Optional[str], ip_address: Optional[str]) -> Tuple[str, str, UserSession]:
    settings = get_settings()
    expires_at = datetime.now(timezone.utc) + timedelta(days=settings.refresh_token_expire_days)
    session = UserSession(
        user_id=user.id,
        refresh_token_hash='pending',
        expires_at=expires_at,
        user_agent=user_agent,
        ip_address=ip_address,
    )
    db.add(session)
    db.flush()

    access_token = create_access_token(user.id, user.role, session.id)
    refresh_token = create_refresh_token(user.id, user.role, session.id)
    session.refresh_token_hash = hash_token(refresh_token)
    audit(db, user_id=user.id, action='login', resource_type='session', resource_id=session.id, detail={'user_agent': user_agent})
    db.commit()
    db.refresh(session)
    return access_token, refresh_token, session


def refresh_session(db: Session, refresh_token: str, *, user_agent: Optional[str], ip_address: Optional[str]) -> Tuple[str, str, User]:
    try:
        payload = decode_token(refresh_token)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='Invalid refresh token') from exc

    if payload.get('typ') != 'refresh':
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='Invalid refresh token type')

    session = db.scalar(select(UserSession).where(UserSession.id == payload.get('sid')))
    if session is None or session.revoked_at is not None or session.refresh_token_hash != hash_token(refresh_token):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='Session unavailable')

    if session.expires_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='Refresh token expired')

    user = db.scalar(select(User).where(User.id == session.user_id))
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='User unavailable')

    session.revoked_at = datetime.now(timezone.utc)
    access_token, new_refresh_token, _ = create_session_tokens(db, user, user_agent=user_agent, ip_address=ip_address)
    return access_token, new_refresh_token, user


def revoke_session(db: Session, refresh_token: Optional[str]) -> None:
    if not refresh_token:
        db.commit()
        return
    try:
        payload = decode_token(refresh_token)
    except Exception:
        db.commit()
        return
    session = db.scalar(select(UserSession).where(UserSession.id == payload.get('sid')))
    if session is not None and session.revoked_at is None:
        session.revoked_at = datetime.now(timezone.utc)
        audit(db, user_id=session.user_id, action='logout', resource_type='session', resource_id=session.id, detail={})
    db.commit()


def create_user(db: Session, *, username: str, password: str, role: str) -> User:
    if get_user_by_username(db, username) is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail='Username already exists')
    user = User(username=username, password_hash=hash_password(password), role=role, is_active=True)
    db.add(user)
    db.flush()
    ensure_user_workspace(db, user)
    audit(db, user_id=user.id, action='user.created', resource_type='user', resource_id=user.id, detail={'role': role})
    db.commit()
    db.refresh(user)
    return user
