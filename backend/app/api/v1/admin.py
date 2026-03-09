from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import require_admin
from app.core.security import hash_password
from app.models import User
from app.repos.user_repo import list_users
from app.schemas.common import AdminPasswordReset, AdminUserCreate, AdminUserStateUpdate, ApiMessage, UserOut
from app.services.auth import create_user


router = APIRouter(prefix='/admin', tags=['admin'])


@router.get('/users', response_model=list[UserOut])
def admin_list_users(db: Session = Depends(get_db), current_user=Depends(require_admin)):
    del current_user
    return [UserOut.model_validate(user) for user in list_users(db)]


@router.post('/users', response_model=UserOut, status_code=status.HTTP_201_CREATED)
def admin_create_user(payload: AdminUserCreate, db: Session = Depends(get_db), current_user=Depends(require_admin)):
    del current_user
    user = create_user(db, username=payload.username, password=payload.password, role=payload.role)
    return UserOut.model_validate(user)


@router.post('/users/{user_id}/reset-password', response_model=ApiMessage)
def admin_reset_password(user_id: str, payload: AdminPasswordReset, db: Session = Depends(get_db), current_user=Depends(require_admin)):
    del current_user
    user = db.scalar(select(User).where(User.id == user_id))
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='User not found')
    user.password_hash = hash_password(payload.password)
    db.commit()
    return ApiMessage(message='password reset')


@router.patch('/users/{user_id}/state', response_model=UserOut)
def admin_update_user_state(user_id: str, payload: AdminUserStateUpdate, db: Session = Depends(get_db), current_user=Depends(require_admin)):
    del current_user
    user = db.scalar(select(User).where(User.id == user_id))
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='User not found')
    user.is_active = payload.is_active
    db.commit()
    db.refresh(user)
    return UserOut.model_validate(user)
