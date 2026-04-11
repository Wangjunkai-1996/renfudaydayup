from fastapi import APIRouter

from app.api.v1 import admin, auth, dashboard, diagnostics, market, paper, reports, settings, signals, strategy, system, tuning, users


router = APIRouter(prefix='/api/v1')
router.include_router(auth.router)
router.include_router(users.router)
router.include_router(dashboard.router)
router.include_router(market.router)
router.include_router(strategy.router)
router.include_router(signals.router)
router.include_router(paper.router)
router.include_router(reports.router)
router.include_router(diagnostics.router)
router.include_router(tuning.router)
router.include_router(admin.router)
router.include_router(settings.router)
router.include_router(system.router)
