#!/usr/bin/env python3
from __future__ import annotations

import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
BACKEND_DIR = ROOT_DIR / 'backend'
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.core.database import SessionLocal, create_schema  # noqa: E402
from app.models import PaperAccount, PaperOrder, PaperPosition, Signal, StrategyConfig, User, WatchlistItem  # noqa: E402
from app.repos.user_repo import get_user_by_username  # noqa: E402
from app.services.auth import create_user  # noqa: E402


LEGACY_DB_PATH = ROOT_DIR / 'data' / 'signals.db'


def _parse_dt(date_value: str, time_value: str) -> datetime:
    try:
        return datetime.fromisoformat(f'{date_value}T{time_value}').replace(tzinfo=timezone.utc)
    except Exception:
        return datetime.now(timezone.utc)


def import_legacy() -> None:
    if not LEGACY_DB_PATH.exists():
        print(f'legacy database not found: {LEGACY_DB_PATH}')
        return

    create_schema()

    with SessionLocal() as db:
        user = get_user_by_username(db, 'legacy_admin')
        if user is None:
            user = create_user(db, username='legacy_admin', password='ChangeMe123!', role='admin')

        conn = sqlite3.connect(str(LEGACY_DB_PATH))
        conn.row_factory = sqlite3.Row

        table_names = {row['name'] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}

        if 'signals' in table_names:
            for row in conn.execute('SELECT * FROM signals ORDER BY created_at DESC'):
                exists = db.query(Signal).filter(Signal.id == str(row['id'])).first()
                if exists is not None:
                    continue
                db.add(
                    Signal(
                        id=str(row['id']),
                        user_id=user.id,
                        symbol=str(row['code']).lower(),
                        name=str(row['name'] or ''),
                        side=str(row['type'] or 'BUY'),
                        level=str(row['level'] or 'normal'),
                        price=float(row['price'] or 0),
                        status=str(row['status'] or 'pending'),
                        description=str(row['desc'] or ''),
                        occurred_at=_parse_dt(str(row['date'] or datetime.now().date()), str(row['time'] or '09:30:00')),
                        meta_json={'legacy_seq_no': row['seq_no'] if 'seq_no' in row.keys() else None},
                    )
                )

        if 'paper_account' in table_names:
            row = conn.execute('SELECT * FROM paper_account WHERE id=1').fetchone()
            if row is not None and db.query(PaperAccount).filter(PaperAccount.user_id == user.id).first() is None:
                db.add(PaperAccount(user_id=user.id, starting_cash=float(row['starting_cash'] or 0), cash=float(row['cash'] or 0), realized_pnl=float(row['realized_pnl'] or 0)))

        if 'paper_positions' in table_names:
            for row in conn.execute('SELECT * FROM paper_positions'):
                db.add(
                    PaperPosition(
                        user_id=user.id,
                        symbol=str(row['code']).lower(),
                        name=str(row['name'] or ''),
                        quantity=int(row['amount'] or 0),
                        available_quantity=int(row['available_amount'] or 0),
                        avg_cost=float(row['avg_cost'] or 0),
                        last_price=float(row['last_price'] or 0),
                    )
                )

        if 'paper_orders' in table_names:
            for row in conn.execute('SELECT * FROM paper_orders ORDER BY created_at DESC LIMIT 500'):
                db.add(
                    PaperOrder(
                        user_id=user.id,
                        signal_id=str(row['signal_id']) if row['signal_id'] else None,
                        symbol=str(row['code']).lower(),
                        side=str(row['side'] or 'BUY'),
                        status=str(row['status'] or 'created'),
                        quantity=int(row['amount'] or 0),
                        price=float(row['price'] or 0),
                        reason=str(row['reason'] or ''),
                        created_at=datetime.now(timezone.utc),
                    )
                )

        if 'paper_base_config' in table_names:
            for row in conn.execute('SELECT * FROM paper_base_config'):
                symbol = str(row['code']).lower()
                if db.query(WatchlistItem).filter(WatchlistItem.user_id == user.id, WatchlistItem.symbol == symbol).first() is None:
                    db.add(WatchlistItem(user_id=user.id, symbol=symbol, display_name=str(row['name'] or symbol), notes='imported from legacy'))

        if db.query(StrategyConfig).filter(StrategyConfig.user_id == user.id).first() is None:
            db.add(StrategyConfig(user_id=user.id, config_json={'imported_from_legacy': True}))

        db.commit()
        conn.close()
        print('legacy import complete for user legacy_admin')


if __name__ == '__main__':
    import_legacy()
