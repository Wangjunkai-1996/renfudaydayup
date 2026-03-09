from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models import StrategyConfig, StrategySnapshot
from app.schemas.common import ApiMessage, StrategyConfigOut, StrategySnapshotOut
from app.schemas.inputs import StrategyConfigUpdate, StrategyRollbackRequest, StrategySnapshotCreate


router = APIRouter(prefix='/strategy', tags=['strategy'])


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
    config = _ensure_strategy_config(db, current_user.id)
    return StrategyConfigOut(id=config.id, user_id=config.user_id, config_json=config.config_json, updated_at=config.updated_at)


@router.put('/config', response_model=StrategyConfigOut)
def update_strategy_config(payload: StrategyConfigUpdate, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    config = _ensure_strategy_config(db, current_user.id)
    config.config_json = payload.config_json
    db.commit()
    db.refresh(config)
    return StrategyConfigOut(id=config.id, user_id=config.user_id, config_json=config.config_json, updated_at=config.updated_at)


@router.get('/snapshots', response_model=list[StrategySnapshotOut])
def list_strategy_snapshots(db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    rows = list(db.scalars(select(StrategySnapshot).where(StrategySnapshot.user_id == current_user.id).order_by(StrategySnapshot.created_at.desc())))
    return [StrategySnapshotOut(id=row.id, label=row.label, config_json=row.config_json, created_at=row.created_at) for row in rows]


@router.post('/snapshots', response_model=StrategySnapshotOut, status_code=status.HTTP_201_CREATED)
def create_strategy_snapshot(payload: StrategySnapshotCreate, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
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
    config = _ensure_strategy_config(db, current_user.id)
    snapshot = db.scalar(select(StrategySnapshot).where(StrategySnapshot.id == payload.snapshot_id, StrategySnapshot.user_id == current_user.id))
    if snapshot is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Strategy snapshot not found')
    config.config_json = snapshot.config_json
    db.commit()
    db.refresh(config)
    return StrategyConfigOut(id=config.id, user_id=config.user_id, config_json=config.config_json, updated_at=config.updated_at)
