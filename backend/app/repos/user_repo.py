from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import User


def get_user_by_username(db: Session, username: str) -> Optional[User]:
    return db.scalar(select(User).where(User.username == username))


def list_users(db: Session) -> list[User]:
    return list(db.scalars(select(User).order_by(User.created_at.desc())))
