from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.api.v1.router import router as api_router
from app.core.config import get_settings
from app.core.database import create_schema
from app.services.bootstrap import ensure_bootstrap_data
from app.services.legacy import build_legacy_mount
from app.ws.router import router as ws_router
from app.core.database import SessionLocal


settings = get_settings()


@asynccontextmanager
async def lifespan(_: FastAPI):
    if settings.auto_create_schema:
        create_schema()
    with SessionLocal() as db:
        ensure_bootstrap_data(db)
    yield


app = FastAPI(title=settings.app_name, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin],
    allow_credentials=True,
    allow_methods=['*'],
    allow_headers=['*'],
)

app.include_router(api_router)
app.include_router(ws_router)

@app.get('/')
def root():
    return JSONResponse(
        {
            'name': settings.app_name,
            'environment': settings.environment,
            'routes': {'app': '/app', 'api': '/api/v1', 'legacy': '/legacy', 'ws': '/ws/v1/stream'},
        }
    )


frontend_dist = Path(__file__).resolve().parents[2] / 'frontend' / 'dist'
if frontend_dist.exists():
    app.mount('/app', StaticFiles(directory=frontend_dist, html=True), name='frontend')

if settings.mount_legacy_app:
    legacy_mount = build_legacy_mount()
    if legacy_mount is not None:
        app.mount('/legacy', legacy_mount)
