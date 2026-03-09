from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models import PaperAccount, PaperBaseConfig, PaperOrder, PaperPosition, WatchlistItem
from app.schemas.common import ApiMessage, PaperAccountOut, PaperBaseConfigOut, PaperOrderOut, PaperPositionOut
from app.schemas.inputs import PaperBaseConfigInput, PaperBaseConfigSeedRequest, PaperResetRequest


router = APIRouter(prefix='/paper', tags=['paper'])


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
    }


@router.post('/reset', response_model=ApiMessage)
def reset_paper(payload: PaperResetRequest, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
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
    rows = list(db.scalars(select(PaperBaseConfig).where(PaperBaseConfig.user_id == current_user.id).order_by(PaperBaseConfig.symbol.asc())))
    return [PaperBaseConfigOut.model_validate(row) for row in rows]


@router.put('/base-config', response_model=PaperBaseConfigOut)
def upsert_paper_base_config(payload: PaperBaseConfigInput, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
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


@router.post('/base-config/seed', response_model=ApiMessage)
def seed_paper_base_config(payload: PaperBaseConfigSeedRequest, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
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
    return ApiMessage(message='base config seeded')
