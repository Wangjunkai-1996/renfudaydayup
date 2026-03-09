from __future__ import annotations

import importlib
import logging
import sys
from pathlib import Path
from typing import Optional

from starlette.middleware.wsgi import WSGIMiddleware


logger = logging.getLogger(__name__)


def build_legacy_mount() -> Optional[WSGIMiddleware]:
    repo_root = Path(__file__).resolve().parents[3]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))
    try:
        legacy_module = importlib.import_module('app')
        legacy_app = getattr(legacy_module, 'app', None)
        if legacy_app is None:
            return None
        return WSGIMiddleware(legacy_app)
    except Exception as exc:
        logger.warning('legacy app mount skipped: %s', exc)
        return None
