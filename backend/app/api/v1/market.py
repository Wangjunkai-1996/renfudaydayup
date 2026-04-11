from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db
from app.core.deps import get_current_user
from app.domain.legacy_facade import (
    build_legacy_market_workbench,
    can_use_legacy_bridge,
    get_legacy_market_context,
    list_legacy_watchlist_items,
)
from app.models import MarketCache, MarketInstrument, WatchlistItem
from app.schemas.common import ApiMessage, MarketPulseItem, WatchlistItemOut
from app.schemas.inputs import WatchlistCreate, WatchlistReorderInput


router = APIRouter(tags=['market'])


def _use_legacy(current_user) -> bool:
    settings = get_settings()
    return can_use_legacy_bridge(username=current_user.username, bootstrap_username=settings.bootstrap_admin_username)


def _serialize_watchlist_items(rows: list[WatchlistItem], market_rows: dict[str, MarketCache]) -> list[dict]:
    items = []
    for item in rows:
        market = market_rows.get(item.symbol)
        items.append(
            {
                'id': item.id,
                'symbol': item.symbol,
                'display_name': item.display_name or (market.extra_json.get('name', item.symbol) if market else item.symbol),
                'notes': item.notes,
                'sort_order': item.sort_order,
                'market': {
                    'last_price': float(market.last_price) if market else None,
                    'change_pct': float(market.change_pct) if market else None,
                    'updated_at': market.updated_at if market else None,
                },
            }
        )
    return items


def _build_next_workbench(db: Session, current_user, symbols: list[str], limit_points: int = 180) -> dict:
    if not symbols:
        rows = list(
            db.scalars(
                select(WatchlistItem)
                .where(WatchlistItem.user_id == current_user.id)
                .order_by(WatchlistItem.sort_order.asc(), WatchlistItem.created_at.asc())
                .limit(6)
            )
        )
        symbols = [row.symbol for row in rows]
    market_rows = {
        row.symbol: row
        for row in db.scalars(select(MarketCache).where(MarketCache.symbol.in_(symbols))).all()
    } if symbols else {}
    instrument_rows = {
        row.symbol: row
        for row in db.scalars(select(MarketInstrument).where(MarketInstrument.symbol.in_(symbols))).all()
    } if symbols else {}
    now = datetime.now(timezone.utc)
    items = []
    for symbol in symbols:
        market = market_rows.get(symbol)
        instrument = instrument_rows.get(symbol)
        name = ''
        if instrument is not None:
            name = instrument.name
        elif market is not None:
            name = str(market.extra_json.get('name') or symbol)
        else:
            name = symbol
        last_price = float(market.last_price) if market is not None else 0.0
        prev_close = float(market.prev_close) if market is not None else last_price
        open_price = float(market.open_price) if market is not None else last_price
        points = []
        for index in range(max(60, min(limit_points, 240))):
            ts = now - timedelta(minutes=max(60, min(limit_points, 240)) - index)
            points.append(
                {
                    'time': ts.astimezone(timezone.utc).strftime('%H:%M'),
                    'price': last_price,
                    'vwap': last_price,
                    'ts': ts.timestamp(),
                }
            )
        change_pct = round((last_price - prev_close) / prev_close * 100, 2) if prev_close else 0.0
        is_st = 'ST' in name.upper()
        limit_pct = 0.05 if is_st else 0.10
        items.append(
            {
                'symbol': symbol,
                'name': name,
                'market': {
                    'last_price': last_price,
                    'change_pct': change_pct,
                    'vwap': last_price,
                    'open_price': open_price,
                    'prev_close': prev_close,
                    'updated_at': market.updated_at.isoformat() if market is not None and market.updated_at else now.isoformat(),
                },
                'series': points,
                'annotations': {
                    'prev_close': prev_close or None,
                    'open_price': open_price or None,
                    'limit_up': round(prev_close * (1 + limit_pct), 4) if prev_close else None,
                    'limit_down': round(prev_close * (1 - limit_pct), 4) if prev_close else None,
                    'r_breaker': {},
                },
                'context': {
                    'trend': '新用户默认工作区数据已就绪',
                    'industry': instrument.sector if instrument is not None else '',
                    'news': [],
                },
            }
        )
    return {'symbols': symbols, 'active_symbol': symbols[0] if symbols else None, 'items': items, 'source': 'next', 'updated_at': now.isoformat()}


@router.get('/market/pulse', response_model=list[MarketPulseItem])
def market_pulse(db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    if _use_legacy(current_user):
        workbench = build_legacy_market_workbench(limit_points=60)
        return [
            MarketPulseItem(
                symbol=item['symbol'],
                name=item['name'],
                last_price=float(item['market'].get('last_price') or 0.0),
                change_pct=float(item['market'].get('change_pct') or 0.0),
                updated_at=datetime.now(timezone.utc),
            )
            for item in workbench.get('items', [])[:12]
        ]

    rows = list(db.scalars(select(MarketCache).order_by(func.abs(MarketCache.change_pct).desc()).limit(12)))
    return [
        MarketPulseItem(
            symbol=row.symbol,
            name=row.extra_json.get('name', row.symbol),
            last_price=float(row.last_price),
            change_pct=float(row.change_pct),
            updated_at=row.updated_at,
        )
        for row in rows
    ]


@router.get('/market/watchlist')
def watchlist_market(db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    items = list(
        db.scalars(
            select(WatchlistItem)
            .where(WatchlistItem.user_id == current_user.id)
            .order_by(WatchlistItem.sort_order.asc(), WatchlistItem.created_at.asc())
        )
    )
    if not items and _use_legacy(current_user):
        return list_legacy_watchlist_items(limit=12)
    symbols = [item.symbol for item in items]
    market_rows = {row.symbol: row for row in db.scalars(select(MarketCache).where(MarketCache.symbol.in_(symbols))).all()} if symbols else {}
    return _serialize_watchlist_items(items, market_rows)


@router.get('/market/workbench')
def market_workbench(
    symbols: str = Query(default=''),
    limit_points: int = Query(default=240, ge=30, le=480),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    parsed_symbols = [part.strip().lower() for part in symbols.split(',') if part.strip()]
    if _use_legacy(current_user):
        return build_legacy_market_workbench(symbols=parsed_symbols or None, limit_points=limit_points)
    return _build_next_workbench(db, current_user, parsed_symbols, limit_points=limit_points)


@router.get('/market/context/{symbol}')
def market_context(symbol: str, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    normalized_symbol = symbol.strip().lower()
    if _use_legacy(current_user):
        return get_legacy_market_context(normalized_symbol)
    instrument = db.scalar(select(MarketInstrument).where(MarketInstrument.symbol == normalized_symbol))
    if instrument is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Instrument not found')
    return {
        'symbol': instrument.symbol,
        'name': instrument.name,
        'context': {
            'trend': '新用户上下文数据已接通',
            'industry': instrument.sector,
            'news': [],
        },
        'source': 'next',
    }


@router.get('/instruments/search')
def search_instruments(q: str = Query(min_length=1), db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    del current_user
    pattern = f'%{q.strip()}%'
    rows = list(
        db.scalars(
            select(MarketInstrument)
            .where(or_(MarketInstrument.symbol.ilike(pattern), MarketInstrument.name.ilike(pattern)))
            .order_by(MarketInstrument.symbol.asc())
            .limit(20)
        )
    )
    return [{'symbol': row.symbol, 'name': row.name, 'exchange': row.exchange, 'sector': row.sector} for row in rows]


@router.post('/watchlist', response_model=WatchlistItemOut, status_code=status.HTTP_201_CREATED)
def create_watchlist_item(payload: WatchlistCreate, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    symbol = payload.symbol.strip().lower()
    existing = db.scalar(select(WatchlistItem).where(WatchlistItem.user_id == current_user.id, WatchlistItem.symbol == symbol))
    if existing is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail='Symbol already in watchlist')
    next_sort = (db.scalar(select(func.max(WatchlistItem.sort_order)).where(WatchlistItem.user_id == current_user.id)) or 0) + 1
    display_name = payload.display_name.strip()
    if not display_name:
        instrument = db.scalar(select(MarketInstrument).where(MarketInstrument.symbol == symbol))
        if instrument is not None:
            display_name = instrument.name
        else:
            market = db.scalar(select(MarketCache).where(MarketCache.symbol == symbol))
            display_name = str(market.extra_json.get('name') or symbol) if market is not None else symbol
    item = WatchlistItem(user_id=current_user.id, symbol=symbol, display_name=display_name, notes=payload.notes, sort_order=next_sort)
    db.add(item)
    db.commit()
    db.refresh(item)
    return WatchlistItemOut.model_validate(item)


@router.post('/watchlist/reorder')
def reorder_watchlist(payload: WatchlistReorderInput, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    requested = [symbol.strip().lower() for symbol in payload.symbols if symbol.strip()]
    rows = list(db.scalars(select(WatchlistItem).where(WatchlistItem.user_id == current_user.id)))
    row_map = {row.symbol: row for row in rows}
    final_symbols = [symbol for symbol in requested if symbol in row_map]
    final_symbols.extend(symbol for symbol in row_map.keys() if symbol not in final_symbols)
    for index, symbol in enumerate(final_symbols, start=1):
        row_map[symbol].sort_order = index
    db.commit()
    market_rows = {
        row.symbol: row
        for row in db.scalars(select(MarketCache).where(MarketCache.symbol.in_(final_symbols))).all()
    } if final_symbols else {}
    ordered_rows = [row_map[symbol] for symbol in final_symbols]
    return {'success': True, 'items': _serialize_watchlist_items(ordered_rows, market_rows)}


@router.delete('/watchlist/{symbol}', response_model=ApiMessage)
def delete_watchlist_item(symbol: str, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    item = db.scalar(select(WatchlistItem).where(WatchlistItem.user_id == current_user.id, WatchlistItem.symbol == symbol.lower()))
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Watchlist item not found')
    db.delete(item)
    db.commit()
    remaining = list(
        db.scalars(
            select(WatchlistItem)
            .where(WatchlistItem.user_id == current_user.id)
            .order_by(WatchlistItem.sort_order.asc(), WatchlistItem.created_at.asc())
        )
    )
    for index, row in enumerate(remaining, start=1):
        row.sort_order = index
    db.commit()
    return ApiMessage(message=f'removed {symbol.lower()}')
