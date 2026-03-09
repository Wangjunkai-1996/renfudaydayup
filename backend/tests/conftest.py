from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


@pytest.fixture()
def client(tmp_path, monkeypatch):
    db_path = tmp_path / 'renfu-next-test.db'
    monkeypatch.setenv('DATABASE_URL', 'sqlite+pysqlite:///' + str(db_path))
    monkeypatch.setenv('AUTO_CREATE_SCHEMA', '1')
    monkeypatch.setenv('MOUNT_LEGACY_APP', '0')
    monkeypatch.setenv('FRONTEND_ORIGIN', 'http://localhost:5173')
    monkeypatch.setenv('BOOTSTRAP_ADMIN_USERNAME', 'legacy_admin')
    monkeypatch.setenv('BOOTSTRAP_ADMIN_PASSWORD', 'ChangeMe123!')

    for module_name in [
        'app.core.config',
        'app.core.database',
        'app.models',
        'app.models.base',
        'app.models.entities',
        'app.services.bootstrap',
        'app.main',
    ]:
        if module_name in sys.modules:
            importlib.reload(sys.modules[module_name])

    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as test_client:
        yield test_client
