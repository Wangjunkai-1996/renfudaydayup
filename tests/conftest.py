import importlib
import os
import sys
from pathlib import Path

import pytest

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))
os.chdir(str(ROOT_DIR))


@pytest.fixture
def load_app(tmp_path, monkeypatch):
    data_dir = tmp_path / 'data'

    def _load(api_token=''):
        monkeypatch.setenv('RENFU_DATA_DIR', str(data_dir))
        monkeypatch.setenv('SKIP_WATCHLIST_RESTORE', '1')
        if api_token:
            monkeypatch.setenv('API_AUTH_TOKEN', api_token)
        else:
            monkeypatch.delenv('API_AUTH_TOKEN', raising=False)

        for name in ('SERVERCHAN_SENDKEY', 'SENDKEY', 'SERVERCHAN_ENABLED', 'SERVERCHAN_NOTIFY_OPEN', 'SERVERCHAN_NOTIFY_RISK', 'SERVERCHAN_TITLE_PREFIX'):
            monkeypatch.delenv(name, raising=False)

        if 'app' in sys.modules:
            del sys.modules['app']
        importlib.invalidate_caches()
        module = importlib.import_module('app')
        module = importlib.reload(module)
        return module

    yield _load

    if 'app' in sys.modules:
        del sys.modules['app']
