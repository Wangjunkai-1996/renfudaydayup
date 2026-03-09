from __future__ import annotations

import random
import time
from datetime import datetime, timezone

from sqlalchemy import select

from app.core.database import SessionLocal
from app.models import MarketCache


def tick_market_cache() -> None:
    with SessionLocal() as db:
        rows = list(db.scalars(select(MarketCache)))
        for row in rows:
            drift = random.uniform(-0.35, 0.35)
            row.change_pct = round(float(row.change_pct) + drift, 2)
            row.last_price = max(0.01, round(float(row.last_price) * (1 + drift / 100), 4))
            row.market_time = datetime.now(timezone.utc)
            row.source = 'worker'
        db.commit()


def main() -> None:
    while True:
        tick_market_cache()
        time.sleep(5)


if __name__ == '__main__':
    main()
