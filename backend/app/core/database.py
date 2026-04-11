from collections.abc import Generator

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings
from app.models.base import Base


settings = get_settings()


def _connect_args(database_url: str) -> dict:
    if database_url.startswith('sqlite'):
        return {'check_same_thread': False}
    return {}


engine = create_engine(
    settings.database_url,
    future=True,
    pool_pre_ping=True,
    connect_args=_connect_args(settings.database_url),
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True, class_=Session)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def ensure_runtime_schema() -> None:
    with engine.begin() as conn:
        inspector = inspect(conn)
        tables = set(inspector.get_table_names())
        if 'watchlists' in tables:
            columns = {column['name'] for column in inspector.get_columns('watchlists')}
            if 'sort_order' not in columns:
                conn.execute(text('ALTER TABLE watchlists ADD COLUMN sort_order INTEGER NOT NULL DEFAULT 0'))


def create_schema() -> None:
    Base.metadata.create_all(bind=engine)
    ensure_runtime_schema()
