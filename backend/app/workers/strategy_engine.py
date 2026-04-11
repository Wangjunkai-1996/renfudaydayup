from __future__ import annotations

import time
from datetime import datetime, timezone

from sqlalchemy import select

from app.core.database import SessionLocal
from app.models import MarketCache, Signal, User, WatchlistItem


def generate_user_signals() -> None:
    with SessionLocal() as db:
        users = list(db.scalars(select(User).where(User.is_active.is_(True))))
        market_map = {row.symbol: row for row in db.scalars(select(MarketCache)).all()}
        now = datetime.now(timezone.utc)
        for user in users:
            watchlist = list(db.scalars(select(WatchlistItem).where(WatchlistItem.user_id == user.id).limit(3)))
            for item in watchlist:
                if item.symbol not in market_map:
                    continue
                row = market_map[item.symbol]
                existing = db.scalar(
                    select(Signal)
                    .where(Signal.user_id == user.id, Signal.symbol == item.symbol)
                    .order_by(Signal.occurred_at.desc())
                )
                if existing is not None:
                    existing_occurred_at = existing.occurred_at
                    if existing_occurred_at.tzinfo is None:
                        existing_occurred_at = existing_occurred_at.replace(tzinfo=timezone.utc)
                    if (now - existing_occurred_at).total_seconds() < 1800:
                        continue
                db.add(
                    Signal(
                        user_id=user.id,
                        symbol=item.symbol,
                        name=item.display_name or row.extra_json.get('name', item.symbol),
                        side='BUY' if float(row.change_pct) >= 0 else 'SELL',
                        level='normal',
                        price=float(row.last_price),
                        status='pending',
                        description='worker stub signal for new stack integration',
                        occurred_at=now,
                        meta_json={'source': 'strategy_engine_stub'},
                    )
                )
        db.commit()


def main() -> None:
    while True:
        generate_user_signals()
        time.sleep(30)


if __name__ == '__main__':
    main()
