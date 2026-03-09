from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db
from app.core.deps import get_current_user
from app.domain.legacy_facade import can_use_legacy_bridge, compute_legacy_edge_diagnostics, compute_legacy_preflight, compute_legacy_slot_performance
from app.models import Signal


router = APIRouter(prefix='/diagnostics', tags=['diagnostics'])


def _use_legacy(current_user) -> bool:
    settings = get_settings()
    return can_use_legacy_bridge(username=current_user.username, bootstrap_username=settings.bootstrap_admin_username)


@router.get('/preflight')
def preflight(date: Optional[str] = Query(default=None), db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    if _use_legacy(current_user):
        return {'success': True, 'source': 'legacy', 'assessment': compute_legacy_preflight(ref_date=date)}

    total = db.scalar(select(func.count(Signal.id)).where(Signal.user_id == current_user.id)) or 0
    return {'success': True, 'source': 'next', 'assessment': {'level': 'ok' if total < 1000 else 'warn', 'completed': total, 'message': '新前后端链路已接通。'}}


@router.get('/slot-performance')
def slot_performance(days: int = Query(default=10, ge=1, le=120), date: Optional[str] = Query(default=None), db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    if _use_legacy(current_user):
        payload = compute_legacy_slot_performance(days=days, end_date=date)
        payload['source'] = 'legacy'
        return payload

    del db, current_user
    return {'success': True, 'source': 'next', 'performance': [{'slot': '09:30-10:00', 'win_rate': 53.2}, {'slot': '10:00-11:00', 'win_rate': 49.8}], 'hints': ['优先观察开盘半小时', '中段波动偏弱时降低仓位']}


@router.get('/edge-diagnostics')
def edge_diagnostics(days: int = Query(default=15, ge=1, le=120), date: Optional[str] = Query(default=None), focus: Optional[str] = Query(default=None), db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    if _use_legacy(current_user):
        payload = compute_legacy_edge_diagnostics(days=days, end_date=date, focus_code=focus)
        payload['source'] = 'legacy'
        return payload

    del db, current_user
    return {'success': True, 'source': 'next', 'diagnostics': {'summary': '新架构已支持边际诊断 API，后续可替换为旧策略实算结果。', 'suggestions': [{'path': 'risk_profile.edge_min', 'value': 0.12}]}}
