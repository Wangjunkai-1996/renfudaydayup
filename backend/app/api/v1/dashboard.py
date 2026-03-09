from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user
from app.schemas.common import DashboardSummary, DiagnosticsOverview
from app.services.dashboard import build_dashboard_summary, build_diagnostics_overview


router = APIRouter(prefix='/dashboard', tags=['dashboard'])


@router.get('/summary', response_model=DashboardSummary)
def summary(db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    return build_dashboard_summary(db, current_user)


@router.get('/diagnostics-overview', response_model=DiagnosticsOverview)
def diagnostics_overview(db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    return build_diagnostics_overview(db, current_user)
