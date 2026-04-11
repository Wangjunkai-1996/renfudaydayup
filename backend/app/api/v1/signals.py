from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db
from app.core.deps import get_current_user
from app.domain.legacy_facade import can_use_legacy_bridge, explain_legacy_signal, get_legacy_signal, list_legacy_signals
from app.models import Signal, SignalExplanation
from app.schemas.common import SignalExplanationOut, SignalOut


router = APIRouter(prefix='/signals', tags=['signals'])


def _use_legacy(current_user) -> bool:
    settings = get_settings()
    return can_use_legacy_bridge(username=current_user.username, bootstrap_username=settings.bootstrap_admin_username)


@router.get('', response_model=list[SignalOut])
def list_signals(
    status_filter: Optional[str] = Query(default=None, alias='status'),
    side_filter: Optional[str] = Query(default=None, alias='side'),
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    if _use_legacy(current_user):
        return list_legacy_signals(status_filter=status_filter, side_filter=side_filter, limit=limit)

    stmt = select(Signal).where(Signal.user_id == current_user.id)
    if status_filter:
        stmt = stmt.where(Signal.status == status_filter)
    if side_filter:
        stmt = stmt.where(Signal.side == side_filter)
    rows = list(db.scalars(stmt.order_by(desc(Signal.occurred_at)).limit(limit)))
    return [SignalOut.model_validate(row) for row in rows]


@router.get('/{signal_id}', response_model=SignalOut)
def get_signal(signal_id: str, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    if _use_legacy(current_user):
        signal = get_legacy_signal(signal_id)
        if signal is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Signal not found')
        return signal

    signal = db.scalar(select(Signal).where(Signal.id == signal_id, Signal.user_id == current_user.id))
    if signal is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Signal not found')
    return SignalOut.model_validate(signal)


@router.get('/{signal_id}/explain')
def explain_signal(signal_id: str, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    if _use_legacy(current_user):
        legacy_explain = explain_legacy_signal(signal_id)
        if legacy_explain is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Signal not found')
        signal = get_legacy_signal(signal_id)
        return {'success': True, 'source': 'legacy', 'signal_id': signal_id, 'signal': signal, 'explain': legacy_explain}

    signal = db.scalar(select(Signal).where(Signal.id == signal_id, Signal.user_id == current_user.id))
    if signal is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Signal not found')

    explanation = db.scalar(select(SignalExplanation).where(SignalExplanation.signal_id == signal.id))
    if explanation is None:
        explanation = SignalExplanation(
            signal_id=signal.id,
            summary=f'{signal.symbol} {signal.side} 信号基于迁移后的新接口已可解释。',
            factors_json=[
                {'label': 'status', 'value': signal.status},
                {'label': 'level', 'value': signal.level},
                {'label': 'price', 'value': signal.price},
            ],
        )
        db.add(explanation)
        db.commit()
        db.refresh(explanation)
    payload = SignalExplanationOut(signal_id=signal.id, summary=explanation.summary, factors_json=explanation.factors_json, updated_at=explanation.updated_at)
    return {'success': True, 'source': 'next', 'signal_id': signal.id, 'signal': SignalOut.model_validate(signal).model_dump(), 'explain': payload.model_dump()}
