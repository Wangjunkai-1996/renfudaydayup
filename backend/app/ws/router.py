from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlalchemy import desc, select

from app.core.config import get_settings
from app.core.security import decode_token
from app.models import MarketCache, Signal, User
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
    try:
        while True:
            with SessionLocal() as db:
                pulse_rows = list(db.scalars(select(MarketCache).order_by(desc(MarketCache.updated_at)).limit(6)))
                signal_rows = list(db.scalars(select(Signal).where(Signal.user_id == user.id).order_by(desc(Signal.occurred_at)).limit(10)))
            now = datetime.now(timezone.utc).isoformat()
            await websocket.send_json(
                {
                    'type': 'market_snapshot',
                    'scope': 'shared',
                    'ts': now,
                    'payload': [
                        {
                            'symbol': row.symbol,
                            'name': row.extra_json.get('name', row.symbol),
                            'last_price': float(row.last_price),
                            'change_pct': float(row.change_pct),
                        }
                        for row in pulse_rows
                    ],
                }
            )
            await websocket.send_json(
                {
                    'type': 'signal_updated',
                    'scope': 'user',
                    'userId': user.id,
                    'ts': now,
                    'payload': [
                        {
                            'id': row.id,
                            'symbol': row.symbol,
                            'name': row.name,
                            'side': row.side,
                            'status': row.status,
                            'price': float(row.price),
                            'occurred_at': row.occurred_at.isoformat(),
                        }
                        for row in signal_rows
                    ],
                }
            )
            await websocket.send_json({'type': 'system_status', 'scope': 'shared', 'ts': now, 'payload': {'status': 'ok'}})
            await asyncio.sleep(5)
    except WebSocketDisconnect:
        return
