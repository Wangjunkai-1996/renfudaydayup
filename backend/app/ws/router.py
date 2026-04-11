from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlalchemy import desc, select

from app.core.config import get_settings
from app.core.security import decode_token
from app.domain.legacy_facade import (
    build_legacy_diagnostics_overview,
    build_legacy_market_workbench,
    can_use_legacy_bridge,
    list_legacy_signals,
)
from app.models import MarketCache, Signal, User, WatchlistItem
from app.core.database import SessionLocal


router = APIRouter()


async def _load_current_user(websocket: WebSocket) -> Optional[User]:
    settings = get_settings()
    token = websocket.cookies.get(settings.access_cookie_name)
    if not token:
        return None
    try:
        payload = decode_token(token)
    except Exception:
        return None
    if payload.get('typ') != 'access':
        return None
    with SessionLocal() as db:
        return db.scalar(select(User).where(User.id == payload.get('sub'), User.is_active.is_(True)))


@router.websocket('/ws/v1/stream')
async def stream(websocket: WebSocket):
    user = await _load_current_user(websocket)
    if user is None:
        await websocket.close(code=4401)
        return

    await websocket.accept()
    settings = get_settings()
    use_legacy = can_use_legacy_bridge(username=user.username, bootstrap_username=settings.bootstrap_admin_username)
    try:
        while True:
            now = datetime.now(timezone.utc).isoformat()
            if use_legacy:
                workbench = build_legacy_market_workbench(limit_points=120)
                pulse_payload = [
                    {
                        'symbol': item['symbol'],
                        'name': item['name'],
                        'last_price': float(item['market'].get('last_price') or 0.0),
                        'change_pct': float(item['market'].get('change_pct') or 0.0),
                    }
                    for item in workbench.get('items', [])
                ]
                diagnostics = build_legacy_diagnostics_overview()
                signals = list_legacy_signals(limit=12)
                watchlist_quotes = [
                    {
                        'symbol': item['symbol'],
                        'name': item['name'],
                        'last_price': float(item['market'].get('last_price') or 0.0),
                        'change_pct': float(item['market'].get('change_pct') or 0.0),
                    }
                    for item in workbench.get('items', [])
                ]
            else:
                with SessionLocal() as db:
                    pulse_rows = list(db.scalars(select(MarketCache).order_by(desc(MarketCache.updated_at)).limit(6)))
                    signal_rows = list(db.scalars(select(Signal).where(Signal.user_id == user.id).order_by(desc(Signal.occurred_at)).limit(10)))
                    watchlist_rows = list(db.scalars(select(WatchlistItem).where(WatchlistItem.user_id == user.id).order_by(WatchlistItem.sort_order.asc(), WatchlistItem.created_at.asc()).limit(8)))
                    market_map = {row.symbol: row for row in db.scalars(select(MarketCache).where(MarketCache.symbol.in_([item.symbol for item in watchlist_rows]))).all()} if watchlist_rows else {}
                pulse_payload = [
                    {
                        'symbol': row.symbol,
                        'name': row.extra_json.get('name', row.symbol),
                        'last_price': float(row.last_price),
                        'change_pct': float(row.change_pct),
                    }
                    for row in pulse_rows
                ]
                signals = [
                    {
                        'id': row.id,
                        'symbol': row.symbol,
                        'name': row.name,
                        'side': row.side,
                        'status': row.status,
                        'level': row.level,
                        'price': float(row.price),
                        'description': row.description,
                        'occurred_at': row.occurred_at.isoformat(),
                        'meta_json': row.meta_json,
                    }
                    for row in signal_rows
                ]
                watchlist_quotes = [
                    {
                        'symbol': row.symbol,
                        'name': market_map[row.symbol].extra_json.get('name', row.symbol) if row.symbol in market_map else row.display_name or row.symbol,
                        'last_price': float(market_map[row.symbol].last_price) if row.symbol in market_map else 0.0,
                        'change_pct': float(market_map[row.symbol].change_pct) if row.symbol in market_map else 0.0,
                    }
                    for row in watchlist_rows
                ]
                diagnostics = {
                    'preflight': {'headline': '新用户诊断摘要', 'details': {'watchlist_size': len(watchlist_quotes)}},
                    'focus_guard': {'headline': '风控摘要', 'summary': f'最近信号 {len(signals)} 条'},
                }

            await websocket.send_json({'type': 'market_snapshot', 'scope': 'shared', 'ts': now, 'payload': pulse_payload})
            await websocket.send_json({'type': 'market_tick', 'scope': 'shared', 'ts': now, 'payload': pulse_payload})
            await websocket.send_json({'type': 'watchlist_quote', 'scope': 'user', 'userId': user.id, 'ts': now, 'payload': watchlist_quotes})
            await websocket.send_json({'type': 'signal_updated', 'scope': 'user', 'userId': user.id, 'ts': now, 'payload': signals})
            await websocket.send_json({'type': 'diagnostic_updated', 'scope': 'user', 'userId': user.id, 'ts': now, 'payload': diagnostics})
            await websocket.send_json({'type': 'system_status', 'scope': 'shared', 'ts': now, 'payload': {'status': 'ok', 'legacy': use_legacy, 'is_trading': True}})
            await asyncio.sleep(5)
    except WebSocketDisconnect:
        return
