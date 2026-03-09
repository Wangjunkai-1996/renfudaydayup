from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import hash_password
from app.models import MarketCache, MarketInstrument, PaperAccount, StrategyConfig, User


SEED_INSTRUMENTS = [
    {'symbol': 'sh600079', 'name': '人福医药', 'exchange': 'SH', 'sector': '医药'},
    {'symbol': 'sz002438', 'name': '江苏神通', 'exchange': 'SZ', 'sector': '机械'},
    {'symbol': 'sz300402', 'name': '宝色股份', 'exchange': 'SZ', 'sector': '装备'},
]


def ensure_bootstrap_data(db: Session) -> None:
    settings = get_settings()

    admin = db.scalar(select(User).where(User.username == settings.bootstrap_admin_username))
    if admin is None:
        admin = User(
            username=settings.bootstrap_admin_username,
            password_hash=hash_password(settings.bootstrap_admin_password),
            role='admin',
            is_active=True,
        )
        db.add(admin)
        db.flush()
        db.add(StrategyConfig(user_id=admin.id, config_json={'risk_profile': 'balanced', 'max_stocks': 3}))
        db.add(PaperAccount(user_id=admin.id, starting_cash=800000, cash=800000, realized_pnl=0))

    existing_symbols = {row[0] for row in db.execute(select(MarketInstrument.symbol)).all()}
    now = datetime.now(timezone.utc)
    for item in SEED_INSTRUMENTS:
        if item['symbol'] not in existing_symbols:
            db.add(MarketInstrument(**item))
            db.add(
                MarketCache(
                    symbol=item['symbol'],
                    last_price=20.0,
                    change_pct=0.0,
                    open_price=20.0,
                    prev_close=20.0,
                    volume=0,
                    market_time=now,
                    source='seed',
                    extra_json={'name': item['name']},
                )
            )
    db.commit()
