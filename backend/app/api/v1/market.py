from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models import MarketCache, MarketInstrument, WatchlistItem
from app.schemas.common import ApiMessage, MarketPulseItem, WatchlistItemOut
from app.schemas.inputs import WatchlistCreate


router = APIRouter(tags=['market'])


@router.get('/market/pulse', response_model=list[MarketPulseItem])
def market_pulse(db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    del current_user
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
    items = list(db.scalars(select(WatchlistItem).where(WatchlistItem.user_id == current_user.id).order_by(WatchlistItem.created_at.desc())))
    symbols = [item.symbol for item in items]
    if not symbols:
        return []
    market_rows = {row.symbol: row for row in db.scalars(select(MarketCache).where(MarketCache.symbol.in_(symbols))).all()}
    return [
        {
            'id': item.id,
            'symbol': item.symbol,
            'display_name': item.display_name or market_rows.get(item.symbol).extra_json.get('name', item.symbol) if market_rows.get(item.symbol) else item.symbol,
            'notes': item.notes,
            'market': {
                'last_price': float(market_rows[item.symbol].last_price) if item.symbol in market_rows else None,
                'change_pct': float(market_rows[item.symbol].change_pct) if item.symbol in market_rows else None,
                'updated_at': market_rows[item.symbol].updated_at if item.symbol in market_rows else None,
            },
        }
        for item in items
    ]


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
    item = WatchlistItem(user_id=current_user.id, symbol=symbol, display_name=payload.display_name, notes=payload.notes)
    db.add(item)
    db.commit()
    db.refresh(item)
    return WatchlistItemOut.model_validate(item)


@router.delete('/watchlist/{symbol}', response_model=ApiMessage)
def delete_watchlist_item(symbol: str, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    item = db.scalar(select(WatchlistItem).where(WatchlistItem.user_id == current_user.id, WatchlistItem.symbol == symbol.lower()))
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Watchlist item not found')
    db.delete(item)
    db.commit()
    return ApiMessage(message=f'removed {symbol.lower()}')
