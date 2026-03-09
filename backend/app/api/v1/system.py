from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import require_admin


router = APIRouter(prefix='/system', tags=['system'])


@router.get('/health')
def health(db: Session = Depends(get_db), current_user=Depends(require_admin)):
    del current_user
    db.execute(text('SELECT 1'))
    return {'status': 'ok', 'ts': datetime.now(timezone.utc).isoformat(), 'components': {'database': 'ok', 'api': 'ok'}}
