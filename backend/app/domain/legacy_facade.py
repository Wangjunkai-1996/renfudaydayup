from __future__ import annotations

import importlib
import json
import logging
import os
import sqlite3
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional


logger = logging.getLogger(__name__)


REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def get_legacy_db_path() -> Path:
    configured = os.getenv('RENFU_DB_PATH', '').strip()
    if configured:
        return Path(configured)
    return REPO_ROOT / 'data' / 'signals.db'


def has_legacy_db() -> bool:
    return get_legacy_db_path().exists()


def _load_legacy_app() -> Any:
    return importlib.import_module('app')


def _legacy_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(str(get_legacy_db_path()))
    conn.row_factory = sqlite3.Row
    return conn


def _legacy_signal_rows(date_from: Optional[str] = None, date_to: Optional[str] = None) -> List[Dict[str, Any]]:
    if not has_legacy_db():
        return []
    conn = _legacy_conn()
    where = []
    params: List[Any] = []
    if date_from:
        where.append('date >= ?')
        params.append(date_from)
    if date_to:
        where.append('date <= ?')
        params.append(date_to)
    where_sql = f"WHERE {' AND '.join(where)}" if where else ''
    rows = conn.execute(
        f'''
        SELECT date, time, code, name, type, status, profit_pct
        FROM signals
        {where_sql}
        ORDER BY date ASC, time ASC, created_at ASC
        ''',
        tuple(params),
    ).fetchall()
    conn.close()
    return [dict(row) for row in rows]


def query_legacy_history(*, date_q: Optional[str], days_q: int, code_q: str, status_q: str, limit_q: int) -> Dict[str, Any]:
    if not has_legacy_db():
        return {'success': True, 'signals': [], 'daily_stats': [], 'date_stats': None, 'query': {'date': date_q, 'days': days_q, 'code': code_q or None, 'status': status_q or None, 'limit': limit_q}}
    from renfu.history_service import query_signal_history

    conn = _legacy_conn()
    try:
        return query_signal_history(
            conn,
            date_q=date_q,
            days_q=days_q,
            code_q=code_q,
            status_q=status_q,
            limit_q=limit_q,
        )
    finally:
        conn.close()


def build_legacy_periodic_report(*, weeks: int, months: int) -> Dict[str, Any]:
    if not has_legacy_db():
        return {}
    from renfu.periodic_report_service import build_periodic_report

    return build_periodic_report(_legacy_signal_rows, weeks=weeks, months=months)


def get_legacy_daily_report(*, target_date: str, generate_if_missing: bool = True) -> Dict[str, Any]:
    legacy_app = _load_legacy_app()
    report = legacy_app.read_daily_report_json(target_date)
    paths = legacy_app.get_daily_report_paths(target_date)
    if report is None and generate_if_missing:
        report, paths = legacy_app.generate_daily_report(target_date, trigger='next_api_get')
    return {'success': report is not None, 'date': target_date, 'report': report, 'json_path': paths['json'], 'md_path': paths['md']}


def generate_legacy_daily_report(*, target_date: str) -> Dict[str, Any]:
    legacy_app = _load_legacy_app()
    report, paths = legacy_app.generate_daily_report(target_date, trigger='next_api_generate')
    return {'success': True, 'date': target_date, 'report': report, 'json_path': paths['json'], 'md_path': paths['md']}


def list_legacy_daily_reports(*, limit: int) -> Dict[str, Any]:
    legacy_app = _load_legacy_app()
    report_dir = Path(legacy_app.REPORT_DIR)
    report_dir.mkdir(parents=True, exist_ok=True)
    files = sorted([item.name for item in report_dir.glob('*.json')], reverse=True)[:limit]
    items = []
    for name in files:
        date_part = name.replace('.json', '')
        paths = legacy_app.get_daily_report_paths(date_part)
        items.append({'date': date_part, 'json_path': paths['json'], 'md_path': paths['md'], 'exists_md': Path(paths['md']).exists()})
    return {'success': True, 'items': items}


def get_legacy_bundle(*, target_date: str, generate_if_missing: bool = True) -> Dict[str, Any]:
    legacy_app = _load_legacy_app()
    bundle = legacy_app.read_daily_bundle_json(target_date)
    path = legacy_app.get_daily_bundle_path(target_date)
    if bundle is None and generate_if_missing:
        bundle, path = legacy_app.generate_daily_bundle(target_date, trigger='next_api_get')
    return {'success': bundle is not None, 'date': target_date, 'bundle': bundle, 'path': path}


def generate_legacy_bundle(*, target_date: str) -> Dict[str, Any]:
    legacy_app = _load_legacy_app()
    bundle, path = legacy_app.generate_daily_bundle(target_date, trigger='next_api_generate')
    return {'success': True, 'date': target_date, 'bundle': bundle, 'path': path}


def compare_legacy_daily_reports(*, target_date: str, baseline_date: Optional[str]) -> Dict[str, Any]:
    legacy_app = _load_legacy_app()
    baseline = baseline_date or legacy_app.get_default_baseline_date(target_date)
    current_report, _ = legacy_app.get_or_generate_daily_report(target_date, trigger='next_api_compare_current')
    baseline_report, _ = legacy_app.get_or_generate_daily_report(baseline, trigger='next_api_compare_baseline')
    if current_report is None or baseline_report is None:
        return {'success': False, 'msg': 'report not found', 'date': target_date, 'baseline_date': baseline}
    comparison = legacy_app.compare_reports(current_report, baseline_report)
    return {'success': True, 'date': target_date, 'baseline_date': baseline, 'current_report': current_report, 'baseline_report': baseline_report, 'comparison': comparison}


def compute_legacy_preflight(*, ref_date: Optional[str]) -> Dict[str, Any]:
    legacy_app = _load_legacy_app()
    return legacy_app.build_preflight_assessment(ref_date=ref_date, lookback_days=5)


def compute_legacy_slot_performance(*, days: int, end_date: Optional[str]) -> Dict[str, Any]:
    legacy_app = _load_legacy_app()
    performance = legacy_app.compute_slot_performance(days=days, end_date=end_date)
    hints = legacy_app.build_slot_hints(performance)
    return {'success': True, 'performance': performance, 'hints': hints}


def compute_legacy_edge_diagnostics(*, days: int, end_date: Optional[str], focus_code: Optional[str]) -> Dict[str, Any]:
    legacy_app = _load_legacy_app()
    diagnostics = legacy_app.compute_edge_diagnostics(days=days, end_date=end_date, focus_code=focus_code)
    return {'success': True, 'diagnostics': diagnostics}


def suggest_legacy_tuning(*, target_date: str, baseline_date: Optional[str]) -> Dict[str, Any]:
    legacy_app = _load_legacy_app()
    baseline = baseline_date or legacy_app.get_default_baseline_date(target_date)
    suggestion = legacy_app.build_param_suggestion(target_date, baseline_date=baseline)
    path = legacy_app.save_tuning_suggestion(suggestion)
    return {'success': True, 'date': target_date, 'baseline_date': baseline, 'suggestion': suggestion, 'saved_path': path}


def apply_legacy_tuning(*, target_date: str, baseline_date: Optional[str], patch: Dict[str, Any], note: str, save_snapshot: bool = True) -> Dict[str, Any]:
    legacy_app = _load_legacy_app()
    baseline = baseline_date or legacy_app.get_default_baseline_date(target_date)
    suggestion = None
    effective_patch = patch or {}
    if not effective_patch:
        suggestion = legacy_app.build_param_suggestion(target_date, baseline_date=baseline)
        effective_patch = suggestion.get('proposed_patch') or {}
    ok, errors, applied = legacy_app.apply_strategy_patch(effective_patch)
    if not ok:
        return {'success': False, 'errors': errors, 'applied': {}}
    snapshot_id = None
    if save_snapshot:
        snapshot_id, _ = legacy_app.save_param_version(note=note or f'next_api tuning {target_date} vs {baseline}')
    return {'success': True, 'date': target_date, 'baseline_date': baseline, 'applied': applied, 'snapshot_id': snapshot_id, 'strategy_after': legacy_app.get_strategy_snapshot(), 'suggestion': suggestion}


def list_legacy_tuning_history(*, limit: int) -> Dict[str, Any]:
    legacy_app = _load_legacy_app()
    tuning_dir = Path(legacy_app.TUNING_DIR)
    tuning_dir.mkdir(parents=True, exist_ok=True)
    files = sorted([item.name for item in tuning_dir.glob('*.json')], reverse=True)[:limit]
    items = []
    for name in files:
        path = tuning_dir / name
        item = {'file': name, 'path': str(path)}
        try:
            payload = json.loads(path.read_text(encoding='utf-8'))
            item['date'] = payload.get('date')
            item['baseline_date'] = payload.get('baseline_date')
            item['generated_at'] = payload.get('generated_at')
            item['patch_size'] = len(payload.get('proposed_patch') or {})
        except Exception:
            pass
        items.append(item)
    return {'success': True, 'items': items}


def explain_legacy_signal(signal_id: str) -> Optional[Dict[str, Any]]:
    if not has_legacy_db():
        return None
    legacy_app = _load_legacy_app()
    conn = _legacy_conn()
    row = conn.execute(
        '''
        SELECT id, date, time, seq_no, code, name, type, level, price, desc, status, resolved_price, gross_profit_pct, profit_pct, resolve_msg, created_at, resolved_at
        FROM signals
        WHERE id=?
        ''',
        (signal_id,),
    ).fetchone()
    conn.close()
    if row is None:
        return None
    return legacy_app.build_signal_explanation(row)


def can_use_legacy_bridge(*, username: str, bootstrap_username: str) -> bool:
    return bool(has_legacy_db() and username == bootstrap_username)
