from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import WatchlistItem


def list_watchlist(db: Session, user_id: str) -> list[WatchlistItem]:
    return list(db.scalars(select(WatchlistItem).where(WatchlistItem.user_id == user_id).order_by(WatchlistItem.created_at.desc())))
