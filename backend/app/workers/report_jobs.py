from __future__ import annotations

import time
from datetime import datetime, timezone

from sqlalchemy import func, select

from app.core.database import SessionLocal
from app.models import DailyReport, Signal, User


def materialize_daily_reports() -> None:
    today = datetime.now(timezone.utc).date()
    with SessionLocal() as db:
        users = list(db.scalars(select(User).where(User.is_active.is_(True))))
        for user in users:
            report = db.scalar(select(DailyReport).where(DailyReport.user_id == user.id, DailyReport.trade_date == today))
            if report is not None:
                continue
            signals = list(db.scalars(select(Signal).where(Signal.user_id == user.id, func.date(Signal.occurred_at) == today.isoformat())))
            db.add(
                DailyReport(
                    user_id=user.id,
                    trade_date=today,
                    title=f'{today.isoformat()} 自动日报',
                    content_json={
                        'signal_total': len(signals),
                        'success_count': sum(1 for item in signals if item.status == 'success'),
                        'fail_count': sum(1 for item in signals if item.status == 'fail'),
                        'source': 'report_jobs_stub',
                    },
                    created_at=datetime.now(timezone.utc),
                )
            )
        db.commit()


def main() -> None:
    while True:
        materialize_daily_reports()
        time.sleep(300)


if __name__ == '__main__':
    main()
