from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db
from app.core.deps import get_current_user
from app.domain.legacy_facade import (
    can_use_legacy_bridge,
    get_legacy_paper_snapshot,
    reset_legacy_paper_account,
    seed_legacy_base_positions,
    upsert_legacy_paper_base_config,
)
from app.models import PaperAccount, PaperBaseConfig, PaperOrder, PaperPosition, WatchlistItem
from app.schemas.common import ApiMessage, PaperAccountOut, PaperBaseConfigOut, PaperOrderOut, PaperPositionOut
from app.schemas.inputs import PaperBaseConfigInput, PaperBaseConfigSeedRequest, PaperResetRequest


router = APIRouter(prefix='/paper', tags=['paper'])


def _use_legacy(current_user) -> bool:
    settings = get_settings()
    return can_use_legacy_bridge(username=current_user.username, bootstrap_username=settings.bootstrap_admin_username)


def _ensure_paper_account(db: Session, user_id: str, starting_cash: float = 800000) -> PaperAccount:
    account = db.scalar(select(PaperAccount).where(PaperAccount.user_id == user_id))
    if account is None:
        account = PaperAccount(user_id=user_id, starting_cash=starting_cash, cash=starting_cash, realized_pnl=0)
        db.add(account)
        db.commit()
        db.refresh(account)
    return account


@router.get('/account')
def get_paper_account(db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    if _use_legacy(current_user):
        return get_legacy_paper_snapshot(recent_limit=50)

    account = _ensure_paper_account(db, current_user.id)
    positions = list(db.scalars(select(PaperPosition).where(PaperPosition.user_id == current_user.id).order_by(desc(PaperPosition.updated_at)).limit(20)))
    orders = list(db.scalars(select(PaperOrder).where(PaperOrder.user_id == current_user.id).order_by(desc(PaperOrder.created_at)).limit(20)))
    return {
        'account': PaperAccountOut(
            id=account.id,
            user_id=account.user_id,
            starting_cash=float(account.starting_cash),
            cash=float(account.cash),
            realized_pnl=float(account.realized_pnl),
            updated_at=account.updated_at,
        ),
        'positions': [PaperPositionOut.model_validate(item) for item in positions],
        'orders': [PaperOrderOut.model_validate(item) for item in orders],
        'base_configs': list_paper_base_configs(db=db, current_user=current_user),
    }


@router.get('/orders')
def list_paper_orders(limit: int = 50, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    if _use_legacy(current_user):
        return {'success': True, 'source': 'legacy', 'items': get_legacy_paper_snapshot(recent_limit=limit).get('orders', [])}
    rows = list(db.scalars(select(PaperOrder).where(PaperOrder.user_id == current_user.id).order_by(desc(PaperOrder.created_at)).limit(max(1, min(limit, 200)))))
    return {'success': True, 'source': 'next', 'items': [PaperOrderOut.model_validate(item).model_dump() for item in rows]}


@router.post('/reset', response_model=ApiMessage)
def reset_paper(payload: PaperResetRequest, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    if _use_legacy(current_user):
        reset_legacy_paper_account(starting_cash=payload.starting_cash)
        return ApiMessage(message='legacy paper account reset')

    account = _ensure_paper_account(db, current_user.id, payload.starting_cash)
    account.starting_cash = payload.starting_cash
    account.cash = payload.starting_cash
    account.realized_pnl = 0
    for row in db.scalars(select(PaperPosition).where(PaperPosition.user_id == current_user.id)).all():
        db.delete(row)
    for row in db.scalars(select(PaperOrder).where(PaperOrder.user_id == current_user.id)).all():
        db.delete(row)
    db.commit()
    return ApiMessage(message='paper account reset')


@router.get('/base-config', response_model=list[PaperBaseConfigOut])
def list_paper_base_configs(db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    if _use_legacy(current_user):
        snapshot = get_legacy_paper_snapshot(recent_limit=20)
        now = datetime.now(timezone.utc)
        return [
            PaperBaseConfigOut(
                id=item['id'],
                symbol=item['symbol'],
                base_amount=float(item.get('base_amount') or 0.0),
                base_cost=float(item.get('base_cost') or 0.0),
                t_order_amount=float(item.get('t_order_amount') or 0.0),
                t_daily_budget=float(item.get('t_daily_budget') or 0.0),
                t_costline_strength=float(item.get('t_costline_strength') or 1.0),
                enabled=bool(item.get('enabled')),
                updated_at=datetime.fromisoformat(str(item.get('updated_at') or now.isoformat()).replace('Z', '+00:00').replace(' ', 'T')),
            )
            for item in snapshot.get('base_configs', [])
        ]

    rows = list(db.scalars(select(PaperBaseConfig).where(PaperBaseConfig.user_id == current_user.id).order_by(PaperBaseConfig.symbol.asc())))
    return [PaperBaseConfigOut.model_validate(row) for row in rows]


@router.put('/base-config')
def upsert_paper_base_config(payload: PaperBaseConfigInput, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    if _use_legacy(current_user):
        return upsert_legacy_paper_base_config(
            symbol=payload.symbol.lower(),
            base_amount=payload.base_amount,
            base_cost=payload.base_cost,
            t_order_amount=payload.t_order_amount,
            t_daily_budget=payload.t_daily_budget,
            t_costline_strength=payload.t_costline_strength,
            enabled=payload.enabled,
        )

    row = db.scalar(select(PaperBaseConfig).where(PaperBaseConfig.user_id == current_user.id, PaperBaseConfig.symbol == payload.symbol.lower()))
    if row is None:
        row = PaperBaseConfig(user_id=current_user.id, symbol=payload.symbol.lower())
        db.add(row)
    row.base_amount = payload.base_amount
    row.base_cost = payload.base_cost
    row.t_order_amount = payload.t_order_amount
    row.t_daily_budget = payload.t_daily_budget
    row.t_costline_strength = payload.t_costline_strength
    row.enabled = payload.enabled
    db.commit()
    db.refresh(row)
    return PaperBaseConfigOut.model_validate(row)


@router.post('/base-config/seed')
def seed_paper_base_config(payload: PaperBaseConfigSeedRequest, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    if _use_legacy(current_user):
        return seed_legacy_base_positions(reseed=False)

    symbols = payload.symbols or [row.symbol for row in db.scalars(select(WatchlistItem).where(WatchlistItem.user_id == current_user.id)).all()]
    for symbol in symbols:
        existing = db.scalar(select(PaperBaseConfig).where(PaperBaseConfig.user_id == current_user.id, PaperBaseConfig.symbol == symbol.lower()))
        if existing is None:
            db.add(
                PaperBaseConfig(
                    user_id=current_user.id,
                    symbol=symbol.lower(),
                    base_amount=50000,
                    base_cost=0,
                    t_order_amount=10000,
                    t_daily_budget=30000,
                    t_costline_strength=1.0,
                    enabled=True,
                )
            )
    db.commit()
    return {'success': True, 'message': 'base config seeded', 'items': list_paper_base_configs(db=db, current_user=current_user)}
