from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db
from app.core.deps import get_current_user
from app.domain.legacy_facade import apply_legacy_tuning, can_use_legacy_bridge, list_legacy_tuning_history, suggest_legacy_tuning
from app.models import StrategyConfig, TuningHistory
from app.schemas.inputs import TuningApplyRequest


router = APIRouter(prefix='/tuning', tags=['tuning'])


def _use_legacy(current_user) -> bool:
    settings = get_settings()
    return can_use_legacy_bridge(username=current_user.username, bootstrap_username=settings.bootstrap_admin_username)


@router.get('/suggest')
def suggest_tuning(date: Optional[str] = Query(default=None), baseline: Optional[str] = Query(default=None), db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    if _use_legacy(current_user) and date:
        payload = suggest_legacy_tuning(target_date=date, baseline_date=baseline)
        payload['source'] = 'legacy'
        return payload

    config = db.scalar(select(StrategyConfig).where(StrategyConfig.user_id == current_user.id))
    return {
        'success': True,
        'source': 'next',
        'assessment': {'current_profile': config.config_json if config else {}, 'summary': '建议先关注风控边界与仓位强度。'},
        'performance': {'win_rate': 50.0, 'avg_profit': 0.0},
        'hints': ['收紧 max_stocks', '按时段调整 edge_min'],
        'diagnostics': {'patch_preview': {'max_stocks': 2, 'edge_min': 0.12}},
    }


@router.post('/apply')
def apply_tuning(payload: TuningApplyRequest, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    if _use_legacy(current_user):
        result = apply_legacy_tuning(target_date=datetime.now(timezone.utc).date().isoformat(), baseline_date=None, patch=payload.patch, note=payload.note, save_snapshot=True)
        result['source'] = 'legacy'
        return result

    config = db.scalar(select(StrategyConfig).where(StrategyConfig.user_id == current_user.id))
    if config is None:
        config = StrategyConfig(user_id=current_user.id, config_json={})
        db.add(config)
    merged = dict(config.config_json)
    merged.update(payload.patch)
    config.config_json = merged
    history = TuningHistory(
        user_id=current_user.id,
        action='apply',
        patch_json=payload.patch,
        note=payload.note,
        created_at=datetime.now(timezone.utc),
    )
    db.add(history)
    db.commit()
    db.refresh(history)
    return {'success': True, 'source': 'next', 'history_id': history.id, 'config_json': config.config_json}


@router.get('/history')
def tuning_history(limit: int = Query(default=30, ge=1, le=365), db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    if _use_legacy(current_user):
        payload = list_legacy_tuning_history(limit=limit)
        payload['source'] = 'legacy'
        return payload

    rows = list(db.scalars(select(TuningHistory).where(TuningHistory.user_id == current_user.id).order_by(desc(TuningHistory.created_at)).limit(limit)))
    return {'success': True, 'source': 'next', 'items': [{'id': row.id, 'action': row.action, 'patch_json': row.patch_json, 'note': row.note, 'created_at': row.created_at} for row in rows]}
