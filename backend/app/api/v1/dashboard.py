from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db
from app.core.deps import get_current_user
from app.domain.legacy_facade import build_legacy_dashboard_summary, build_legacy_diagnostics_overview, can_use_legacy_bridge
from app.schemas.common import DashboardSummary, DiagnosticsOverview
from app.services.dashboard import build_dashboard_summary, build_diagnostics_overview


router = APIRouter(prefix='/dashboard', tags=['dashboard'])


def _use_legacy(current_user) -> bool:
    settings = get_settings()
    return can_use_legacy_bridge(username=current_user.username, bootstrap_username=settings.bootstrap_admin_username)


@router.get('/summary', response_model=DashboardSummary)
def summary(db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    if _use_legacy(current_user):
        payload = build_legacy_dashboard_summary()
        payload['user'] = current_user
        return payload
    return build_dashboard_summary(db, current_user)


@router.get('/diagnostics-overview', response_model=DiagnosticsOverview)
def diagnostics_overview(db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    if _use_legacy(current_user):
        return build_legacy_diagnostics_overview()
    return build_diagnostics_overview(db, current_user)
