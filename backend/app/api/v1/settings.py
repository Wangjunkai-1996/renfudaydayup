from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user
from app.core.security import clear_auth_cookies, hash_password, verify_password
from app.models import NotificationSetting, User, UserSession
from app.schemas.common import ApiMessage, NotificationSettingsOut, UserOut
from app.schemas.inputs import NotificationSettingsUpdate, SettingsAccountUpdate, SettingsPasswordUpdate


router = APIRouter(prefix='/settings', tags=['settings'])


def _ensure_notification_settings(db: Session, user_id: str) -> NotificationSetting:
    row = db.scalar(select(NotificationSetting).where(NotificationSetting.user_id == user_id))
    if row is None:
        row = NotificationSetting(
            user_id=user_id,
            settings_json={
                'browser_push': True,
                'signal_alert': True,
                'preclose_alert': True,
                'daily_report': True,
                'system_notice': True,
            },
        )
        db.add(row)
        db.commit()
        db.refresh(row)
    return row


@router.put('/account', response_model=UserOut)
def update_account(payload: SettingsAccountUpdate, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    username = payload.username.strip()
    if not username:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail='username is required')
    existing = db.scalar(select(User).where(User.username == username, User.id != current_user.id))
    if existing is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail='username already exists')
    current_user.username = username
    db.commit()
    db.refresh(current_user)
    return UserOut.model_validate(current_user)


@router.put('/password', response_model=ApiMessage)
def update_password(payload: SettingsPasswordUpdate, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    if not verify_password(payload.current_password, current_user.password_hash):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='current password is incorrect')
    if len(payload.new_password.strip()) < 6:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail='new password must be at least 6 characters')
    current_user.password_hash = hash_password(payload.new_password)
    for session in db.scalars(select(UserSession).where(UserSession.user_id == current_user.id, UserSession.revoked_at.is_(None))).all():
        session.revoked_at = datetime.now(timezone.utc)
    db.commit()
    return ApiMessage(message='password updated, please login again on other devices')


@router.post('/logout-all', response_model=ApiMessage)
def logout_all_sessions(request: Request, response: Response, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    del request
    for session in db.scalars(select(UserSession).where(UserSession.user_id == current_user.id, UserSession.revoked_at.is_(None))).all():
        session.revoked_at = datetime.now(timezone.utc)
    db.commit()
    clear_auth_cookies(response)
    return ApiMessage(message='all sessions revoked')


@router.get('/notifications', response_model=NotificationSettingsOut)
def get_notification_settings(db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    row = _ensure_notification_settings(db, current_user.id)
    return NotificationSettingsOut(settings_json=row.settings_json)


@router.put('/notifications', response_model=NotificationSettingsOut)
def update_notification_settings(payload: NotificationSettingsUpdate, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    row = _ensure_notification_settings(db, current_user.id)
    merged = dict(row.settings_json or {})
    merged.update(payload.settings_json or {})
    row.settings_json = merged
    db.commit()
    db.refresh(row)
    return NotificationSettingsOut(settings_json=row.settings_json)
