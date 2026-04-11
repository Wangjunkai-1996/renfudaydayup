from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db
from app.core.deps import get_current_user
from app.domain.legacy_facade import (
    can_use_legacy_bridge,
    get_legacy_strategy_config,
    list_legacy_strategy_snapshots,
    rollback_legacy_strategy_snapshot,
    save_legacy_strategy_snapshot,
    update_legacy_strategy_config,
)
from app.models import StrategyConfig, StrategySnapshot
from app.schemas.common import StrategyConfigOut, StrategySnapshotOut
from app.schemas.inputs import StrategyConfigUpdate, StrategyRollbackRequest, StrategySnapshotCreate


router = APIRouter(prefix='/strategy', tags=['strategy'])


def _use_legacy(current_user) -> bool:
    settings = get_settings()
    return can_use_legacy_bridge(username=current_user.username, bootstrap_username=settings.bootstrap_admin_username)


def _ensure_strategy_config(db: Session, user_id: str) -> StrategyConfig:
    config = db.scalar(select(StrategyConfig).where(StrategyConfig.user_id == user_id))
    if config is None:
        config = StrategyConfig(user_id=user_id, config_json={'risk_profile': 'balanced', 'max_stocks': 3})
        db.add(config)
        db.commit()
        db.refresh(config)
    return config


@router.get('/config', response_model=StrategyConfigOut)
def get_strategy_config(db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    if _use_legacy(current_user):
        return StrategyConfigOut(id='legacy-strategy', user_id=current_user.id, config_json=get_legacy_strategy_config(), updated_at=datetime.now(timezone.utc))
    config = _ensure_strategy_config(db, current_user.id)
    return StrategyConfigOut(id=config.id, user_id=config.user_id, config_json=config.config_json, updated_at=config.updated_at)


@router.put('/config', response_model=StrategyConfigOut)
def update_strategy_config(payload: StrategyConfigUpdate, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    if _use_legacy(current_user):
        result = update_legacy_strategy_config(payload.config_json)
        if not result.get('success'):
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=result.get('errors') or 'invalid legacy strategy config')
        return StrategyConfigOut(id='legacy-strategy', user_id=current_user.id, config_json=result['config_json'], updated_at=datetime.now(timezone.utc))

    config = _ensure_strategy_config(db, current_user.id)
    config.config_json = payload.config_json
    db.commit()
    db.refresh(config)
    return StrategyConfigOut(id=config.id, user_id=config.user_id, config_json=config.config_json, updated_at=config.updated_at)


@router.get('/snapshots', response_model=list[StrategySnapshotOut])
def list_strategy_snapshots(db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    if _use_legacy(current_user):
        return [StrategySnapshotOut(id=row['id'], label=row['label'], config_json=row['config_json'], created_at=row['created_at']) for row in list_legacy_strategy_snapshots(limit=50)]
    rows = list(db.scalars(select(StrategySnapshot).where(StrategySnapshot.user_id == current_user.id).order_by(StrategySnapshot.created_at.desc())))
    return [StrategySnapshotOut(id=row.id, label=row.label, config_json=row.config_json, created_at=row.created_at) for row in rows]


@router.post('/snapshots', response_model=StrategySnapshotOut, status_code=status.HTTP_201_CREATED)
def create_strategy_snapshot(payload: StrategySnapshotCreate, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    if _use_legacy(current_user):
        row = save_legacy_strategy_snapshot(payload.label)
        return StrategySnapshotOut(id=row['id'], label=row['label'], config_json=row['config_json'], created_at=row['created_at'])

    config = _ensure_strategy_config(db, current_user.id)
    snapshot = StrategySnapshot(
        user_id=current_user.id,
        label=payload.label,
        config_json=config.config_json,
        created_at=datetime.now(timezone.utc),
    )
    db.add(snapshot)
    db.commit()
    db.refresh(snapshot)
    return StrategySnapshotOut(id=snapshot.id, label=snapshot.label, config_json=snapshot.config_json, created_at=snapshot.created_at)


@router.post('/rollback', response_model=StrategyConfigOut)
def rollback_strategy(payload: StrategyRollbackRequest, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    if _use_legacy(current_user):
        result = rollback_legacy_strategy_snapshot(payload.snapshot_id)
        if not result.get('success'):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=result.get('message') or result.get('errors') or 'Strategy snapshot not found')
        return StrategyConfigOut(id='legacy-strategy', user_id=current_user.id, config_json=result['config_json'], updated_at=datetime.now(timezone.utc))

    config = _ensure_strategy_config(db, current_user.id)
    snapshot = db.scalar(select(StrategySnapshot).where(StrategySnapshot.id == payload.snapshot_id, StrategySnapshot.user_id == current_user.id))
    if snapshot is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Strategy snapshot not found')
    config.config_json = snapshot.config_json
    db.commit()
    db.refresh(config)
    return StrategyConfigOut(id=config.id, user_id=config.user_id, config_json=config.config_json, updated_at=config.updated_at)
