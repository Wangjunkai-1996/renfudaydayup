from __future__ import annotations

import importlib
import json
import logging
import os
import sqlite3
import sys
from contextlib import nullcontext
from datetime import datetime, timezone
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


def _legacy_state_guard(legacy_app: Any):
    return getattr(legacy_app, 'state_lock', nullcontext())


def _legacy_runtime_dict(legacy_app: Any, attr: str) -> dict[str, Any]:
    value = getattr(legacy_app, attr, {}) or {}
    return value if isinstance(value, dict) else {}


def _legacy_enabled_watchlist_codes(legacy_app: Any) -> list[str]:
    getter = getattr(legacy_app, 'list_enabled_watchlist_codes', None)
    if callable(getter):
        try:
            return [str(symbol).strip().lower() for symbol in list(getter()) if str(symbol).strip()]
        except Exception as exc:
            logger.debug('legacy enabled watchlist read failed: %s', exc)
    return []


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


def _combine_signal_dt(date_value: Optional[str], time_value: Optional[str], resolved_at: Optional[str] = None) -> Optional[str]:
    if resolved_at:
        if 'T' in str(resolved_at):
            return str(resolved_at)
        return str(resolved_at).replace(' ', 'T')
    if not date_value:
        return None
    if time_value:
        return f'{date_value}T{time_value}'
    return f'{date_value}T00:00:00'


def _row_to_signal_dict(row: sqlite3.Row | Dict[str, Any]) -> Dict[str, Any]:
    payload = dict(row)
    return {
        'id': str(payload.get('id') or ''),
        'symbol': str(payload.get('code') or '').lower(),
        'name': str(payload.get('name') or payload.get('code') or ''),
        'side': str(payload.get('type') or ''),
        'level': str(payload.get('level') or 'normal'),
        'price': float(payload.get('price') or 0.0),
        'status': str(payload.get('status') or 'pending'),
        'description': str(payload.get('desc') or ''),
        'occurred_at': _combine_signal_dt(payload.get('date'), payload.get('time')),
        'resolved_at': _combine_signal_dt(payload.get('date'), payload.get('time'), payload.get('resolved_at')),
        'meta_json': {
            'date': payload.get('date'),
            'time': payload.get('time'),
            'resolve_msg': payload.get('resolve_msg'),
            'resolved_price': float(payload.get('resolved_price') or 0.0),
            'gross_profit_pct': float(payload.get('gross_profit_pct') or 0.0),
            'profit_pct': float(payload.get('profit_pct') or 0.0),
            'seq_no': int(payload.get('seq_no') or 0),
        },
    }


def _normalize_news_items(news_items: list[Any]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for item in list(news_items or [])[:12]:
        if isinstance(item, dict):
            normalized.append(
                {
                    'title': str(item.get('title') or item.get('headline') or ''),
                    'summary': str(item.get('summary') or item.get('desc') or ''),
                    'url': str(item.get('url') or ''),
                    'source': str(item.get('source') or ''),
                    'time': str(item.get('time') or item.get('published_at') or ''),
                }
            )
        else:
            normalized.append({'title': str(item), 'summary': '', 'url': '', 'source': '', 'time': ''})
    return normalized


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


def list_legacy_signals(*, status_filter: Optional[str] = None, side_filter: Optional[str] = None, limit: int = 100) -> list[dict[str, Any]]:
    if not has_legacy_db():
        return []
    conn = _legacy_conn()
    where = []
    params: list[Any] = []
    if status_filter:
        where.append('status = ?')
        params.append(status_filter)
    if side_filter:
        where.append('type = ?')
        params.append(side_filter)
    where_sql = f"WHERE {' AND '.join(where)}" if where else ''
    rows = conn.execute(
        f'''
        SELECT id, date, time, code, name, type, level, price, desc, status, resolved_price, gross_profit_pct, profit_pct, resolve_msg, created_at, resolved_at, seq_no
        FROM signals
        {where_sql}
        ORDER BY date DESC, time DESC, created_at DESC
        LIMIT ?
        ''',
        tuple(params + [max(1, min(int(limit), 500))]),
    ).fetchall()
    conn.close()
    return [_row_to_signal_dict(row) for row in rows]


def get_legacy_signal(signal_id: str) -> Optional[dict[str, Any]]:
    if not has_legacy_db():
        return None
    conn = _legacy_conn()
    row = conn.execute(
        '''
        SELECT id, date, time, code, name, type, level, price, desc, status, resolved_price, gross_profit_pct, profit_pct, resolve_msg, created_at, resolved_at, seq_no
        FROM signals
        WHERE id=?
        ''',
        (signal_id,),
    ).fetchone()
    conn.close()
    if row is None:
        return None
    detail = _row_to_signal_dict(row)
    explanation = explain_legacy_signal(signal_id)
    if explanation is not None:
        detail['meta_json']['insights'] = explanation.get('insights') or []
        detail['meta_json']['factors'] = explanation.get('factors') or []
        detail['meta_json']['slot'] = explanation.get('slot')
    return detail


def _ensure_legacy_symbols(symbols: Optional[list[str]] = None, *, limit: int = 3) -> list[str]:
    legacy_app = _load_legacy_app()
    target_symbols = [str(symbol or '').strip().lower() for symbol in list(symbols or []) if str(symbol or '').strip()]
    if not target_symbols:
        target_symbols = _legacy_enabled_watchlist_codes(legacy_app)
    if not target_symbols:
        target_symbols = [str(symbol).strip().lower() for symbol in list(getattr(legacy_app, 'active_stocks', {}).keys())]
    target_symbols = [symbol for symbol in target_symbols if symbol]
    if limit > 0:
        target_symbols = target_symbols[:limit]
    for symbol in list(target_symbols):
        try:
            with _legacy_state_guard(legacy_app):
                already_active = symbol in _legacy_runtime_dict(legacy_app, 'active_stocks')
            if not already_active:
                legacy_app.apply_add_stock(symbol, persist=False)
        except Exception as exc:
            logger.debug('legacy symbol preload failed for %s: %s', symbol, exc)
    return target_symbols


def list_legacy_watchlist_items(limit: int = 8) -> list[dict[str, Any]]:
    if not has_legacy_db():
        return []
    conn = _legacy_conn()
    rows = conn.execute(
        '''
        SELECT code, name, enabled, sort_order, added_at, updated_at
        FROM watchlist
        WHERE enabled=1
        ORDER BY sort_order ASC, added_at ASC, code ASC
        LIMIT ?
        ''',
        (max(1, min(int(limit), 100)),),
    ).fetchall()
    conn.close()
    legacy_app = _load_legacy_app()
    items = []
    for index, row in enumerate(rows):
        code = str(row['code'] or '').strip().lower()
        name = str(row['name'] or '').strip()
        with _legacy_state_guard(legacy_app):
            points = list(_legacy_runtime_dict(legacy_app, 'market_data').get(code, []))
        current_price = float(points[-1].get('price') or 0.0) if points else 0.0
        items.append(
            {
                'id': f'legacy-{code}',
                'symbol': code,
                'display_name': name or code,
                'notes': '',
                'sort_order': int(row['sort_order'] or index),
                'market': {
                    'last_price': current_price or None,
                    'change_pct': None,
                    'updated_at': row['updated_at'],
                },
            }
        )
    return items


def build_legacy_market_workbench(*, symbols: Optional[list[str]] = None, limit_points: int = 240) -> dict[str, Any]:
    legacy_app = _load_legacy_app()
    target_symbols = _ensure_legacy_symbols(symbols, limit=max(1, min(len(symbols or []) or 3, 8)))
    items: list[dict[str, Any]] = []
    for symbol in target_symbols:
        with _legacy_state_guard(legacy_app):
            market_data = _legacy_runtime_dict(legacy_app, 'market_data')
            active_stocks = _legacy_runtime_dict(legacy_app, 'active_stocks')
            stock_contexts = _legacy_runtime_dict(legacy_app, 'stock_contexts')
            stock_extras = _legacy_runtime_dict(legacy_app, 'stock_extras')
            analyzers = _legacy_runtime_dict(legacy_app, 'analyzers')
            points = [dict(point) for point in list(market_data.get(symbol, []))[-max(30, min(int(limit_points), 480)):]]
            active_name = str(active_stocks.get(symbol, ''))
            context = dict(stock_contexts.get(symbol, {}))
            extras = dict(stock_extras.get(symbol, {}))
            analyzer = analyzers.get(symbol)
            r_breaker = dict(getattr(analyzer, 'r_breaker', {}) or {}) if analyzer is not None else {}
        last_price = float(points[-1].get('price') or 0.0) if points else 0.0
        last_vwap = float(points[-1].get('vwap') or 0.0) if points else 0.0
        prev_close = float(extras.get('yest_close') or 0.0)
        open_price = float(extras.get('open_price') or 0.0)
        change_pct = round((last_price - prev_close) / prev_close * 100, 2) if last_price and prev_close else 0.0
        is_st_stock = 'ST' in active_name.upper()
        limit_pct = 0.05 if is_st_stock else 0.10
        items.append(
            {
                'symbol': symbol,
                'name': active_name or symbol,
                'market': {
                    'last_price': last_price,
                    'change_pct': change_pct,
                    'vwap': last_vwap,
                    'open_price': open_price,
                    'prev_close': prev_close,
                    'updated_at': datetime.now(timezone.utc).isoformat(),
                },
                'series': points,
                'annotations': {
                    'prev_close': prev_close or None,
                    'open_price': open_price or None,
                    'limit_up': round(prev_close * (1 + limit_pct), 4) if prev_close else None,
                    'limit_down': round(prev_close * (1 - limit_pct), 4) if prev_close else None,
                    'r_breaker': r_breaker,
                },
                'context': {
                    'trend': str(context.get('trend') or ''),
                    'industry': str(context.get('industry') or ''),
                    'news': _normalize_news_items(context.get('news') or []),
                },
            }
        )
    return {
        'symbols': [item['symbol'] for item in items],
        'active_symbol': items[0]['symbol'] if items else None,
        'items': items,
        'source': 'legacy',
        'updated_at': datetime.now(timezone.utc).isoformat(),
    }


def get_legacy_market_context(symbol: str) -> dict[str, Any]:
    payload = build_legacy_market_workbench(symbols=[symbol], limit_points=120)
    if not payload['items']:
        return {'symbol': symbol, 'context': {'trend': '', 'industry': '', 'news': []}, 'source': 'legacy'}
    item = payload['items'][0]
    return {'symbol': item['symbol'], 'name': item['name'], 'context': item['context'], 'source': 'legacy'}


def get_legacy_paper_snapshot(*, recent_limit: int = 30) -> dict[str, Any]:
    legacy_app = _load_legacy_app()
    with _legacy_state_guard(legacy_app):
        current_state = {
            code: {'price': float(points[-1].get('price') or 0.0)}
            for code, points in _legacy_runtime_dict(legacy_app, 'market_data').items()
            if points
        }
    snapshot = legacy_app.get_paper_snapshot(current_state, recent_limit=recent_limit)
    now_iso = datetime.now(timezone.utc).isoformat()
    positions = [
        {
            'id': f"legacy-pos-{item.get('code')}",
            'symbol': item.get('code'),
            'name': item.get('name'),
            'quantity': int(item.get('total_qty') or 0),
            'available_quantity': int(item.get('available_qty') or 0),
            'avg_cost': float(item.get('avg_cost') or 0.0),
            'last_price': float(item.get('current_price') or 0.0),
            'market_value': float(item.get('market_value') or 0.0),
            'unrealized_pnl': float(item.get('unrealized_pnl') or 0.0),
            'realized_pnl': float(item.get('realized_pnl') or 0.0),
            'updated_at': item.get('updated_at') or now_iso,
        }
        for item in snapshot.get('positions', [])
    ]
    orders = [
        {
            'id': str(item.get('order_id') or ''),
            'signal_id': item.get('signal_id'),
            'symbol': item.get('code'),
            'name': item.get('name'),
            'side': item.get('side'),
            'status': item.get('status'),
            'quantity': int(item.get('qty') or 0),
            'price': float(item.get('price') or 0.0),
            'amount': float(item.get('amount') or 0.0),
            'fee': float(item.get('fee') or 0.0),
            'reason': item.get('reason') or '',
            'created_at': (item.get('created_at') or '').replace(' ', 'T') if item.get('created_at') else now_iso,
        }
        for item in snapshot.get('recent_orders', [])
    ]
    base_configs = [
        {
            'id': f"legacy-base-{item.get('code')}",
            'symbol': item.get('code'),
            'name': item.get('name'),
            'base_amount': float(item.get('base_amount') or 0.0),
            'base_cost': float(item.get('base_cost_line') or 0.0),
            't_order_amount': float(item.get('t_order_amount') or 0.0),
            't_daily_budget': float(item.get('t_daily_budget') or 0.0),
            't_costline_strength': float(item.get('t_costline_strength') or 1.0),
            'enabled': bool(item.get('enabled')),
            'updated_at': item.get('updated_at') or now_iso,
            'remaining_amount': float(item.get('t_remaining_amount') or 0.0),
            'remaining_orders': int(item.get('t_remaining_orders') or 0),
        }
        for item in snapshot.get('base_configs', [])
    ]
    return {
        'account': {
            'id': 'legacy-paper',
            'user_id': 'legacy_admin',
            'starting_cash': float(snapshot.get('starting_cash') or 0.0),
            'cash': float(snapshot.get('cash') or 0.0),
            'market_value': float(snapshot.get('market_value') or 0.0),
            'nav': float(snapshot.get('nav') or 0.0),
            'realized_pnl': float(snapshot.get('realized_pnl') or 0.0),
            'unrealized_pnl': float(snapshot.get('unrealized_pnl') or 0.0),
            'total_pnl': float(snapshot.get('total_pnl') or 0.0),
            'return_pct': float(snapshot.get('return_pct') or 0.0),
            'updated_at': now_iso,
        },
        'positions': positions,
        'orders': orders,
        'base_configs': base_configs,
    }


def reset_legacy_paper_account(*, starting_cash: float = 800000.0) -> dict[str, Any]:
    legacy_app = _load_legacy_app()
    legacy_app.reset_paper_account(starting_cash=starting_cash)
    return get_legacy_paper_snapshot(recent_limit=30)


def upsert_legacy_paper_base_config(*, symbol: str, base_amount: float, base_cost: float, t_order_amount: float, t_daily_budget: float, t_costline_strength: float, enabled: bool) -> dict[str, Any]:
    legacy_app = _load_legacy_app()
    ok, message = legacy_app.upsert_base_config(
        symbol,
        symbol,
        base_amount,
        base_cost,
        enabled=enabled,
        t_order_amount=t_order_amount,
        t_daily_budget=t_daily_budget,
        t_costline_strength=t_costline_strength,
    )
    return {'success': ok, 'message': message, 'items': get_legacy_paper_snapshot(recent_limit=30).get('base_configs', [])}


def seed_legacy_base_positions(*, reseed: bool = False) -> dict[str, Any]:
    legacy_app = _load_legacy_app()
    applied = legacy_app.seed_base_positions(reseed=reseed)
    return {'success': True, 'applied': applied, 'paper': get_legacy_paper_snapshot(recent_limit=30)}


def get_legacy_strategy_config() -> dict[str, Any]:
    legacy_app = _load_legacy_app()
    return legacy_app.get_strategy_snapshot()


def update_legacy_strategy_config(config_json: dict[str, Any]) -> dict[str, Any]:
    legacy_app = _load_legacy_app()
    ok, errors, applied = legacy_app.apply_strategy_patch(config_json)
    return {'success': ok, 'errors': errors, 'applied': applied, 'config_json': legacy_app.get_strategy_snapshot()}


def list_legacy_strategy_snapshots(limit: int = 30) -> list[dict[str, Any]]:
    legacy_app = _load_legacy_app()
    items = []
    for row in legacy_app.list_param_versions(limit=limit):
        items.append(
            {
                'id': str(row.get('id')),
                'label': str(row.get('note') or f"快照 {row.get('id')}").strip(),
                'config_json': row.get('params') or {},
                'created_at': (row.get('created_at') or '').replace(' ', 'T') if row.get('created_at') else datetime.now(timezone.utc).isoformat(),
            }
        )
    return items


def save_legacy_strategy_snapshot(label: str) -> dict[str, Any]:
    legacy_app = _load_legacy_app()
    snapshot_id, snapshot = legacy_app.save_param_version(note=label)
    return {'id': str(snapshot_id), 'label': label or f'快照 {snapshot_id}', 'config_json': snapshot, 'created_at': datetime.now(timezone.utc).isoformat()}


def rollback_legacy_strategy_snapshot(snapshot_id: str) -> dict[str, Any]:
    legacy_app = _load_legacy_app()
    version = legacy_app.get_param_version(int(snapshot_id))
    if not version:
        return {'success': False, 'message': f'param version not found: {snapshot_id}'}
    ok, errors, applied = legacy_app.apply_strategy_patch(version.get('params', {}))
    return {'success': ok, 'errors': errors, 'applied': applied, 'config_json': legacy_app.get_strategy_snapshot(), 'note': version.get('note')}


def build_legacy_dashboard_summary() -> dict[str, Any]:
    conn = _legacy_conn() if has_legacy_db() else None
    signal_counts: dict[str, int] = {}
    if conn is not None:
        for status_value, count in conn.execute('SELECT status, COUNT(*) AS c FROM signals GROUP BY status').fetchall():
            signal_counts[str(status_value or 'unknown')] = int(count or 0)
        conn.close()
    workbench = build_legacy_market_workbench(limit_points=120)
    pulse = []
    for item in workbench.get('items', [])[:6]:
        pulse.append(
            {
                'symbol': item['symbol'],
                'name': item['name'],
                'last_price': float(item['market'].get('last_price') or 0.0),
                'change_pct': float(item['market'].get('change_pct') or 0.0),
                'updated_at': item['market'].get('updated_at'),
            }
        )
    paper = get_legacy_paper_snapshot(recent_limit=10)['account']
    return {
        'pulse': pulse,
        'watchlist_count': len(workbench.get('symbols', [])),
        'signal_counts': signal_counts,
        'paper_summary': {
            'starting_cash': paper.get('starting_cash', 0.0),
            'cash': paper.get('cash', 0.0),
            'realized_pnl': paper.get('realized_pnl', 0.0),
            'market_value': paper.get('market_value', 0.0),
            'nav': paper.get('nav', 0.0),
            'return_pct': paper.get('return_pct', 0.0),
        },
        'alerts': [
            {'level': 'info', 'title': '已桥接 Legacy 实盘逻辑', 'message': 'Dashboard/Market/Signals/Paper 优先展示旧系统真实数据。'},
            {'level': 'info', 'title': 'Legacy 对照入口保留', 'message': '仍可通过 /legacy 对照新旧系统结果。'},
        ],
        'workbench': workbench,
    }


def build_legacy_diagnostics_overview() -> dict[str, Any]:
    preflight = compute_legacy_preflight(ref_date=None)
    slot = compute_legacy_slot_performance(days=10, end_date=None)
    edge = compute_legacy_edge_diagnostics(days=15, end_date=None, focus_code=None)
    history = query_legacy_history(date_q=None, days_q=10, code_q='', status_q='', limit_q=300)
    signals = list(history.get('signals') or [])
    recent_success = sum(1 for item in signals if str(item.get('status') or '') == 'success')
    recent_fail = sum(1 for item in signals if str(item.get('status') or '') == 'fail')
    closed = recent_success + recent_fail
    win_rate = round(recent_success / closed * 100, 1) if closed else None
    return {
        'preflight': {
            'headline': 'Legacy preflight 已接入',
            'details': preflight,
        },
        'focus_guard': {
            'headline': '焦点防守摘要',
            'summary': preflight.get('summary') or preflight.get('message') or '已接入 Legacy 预检结果',
            'raw': preflight,
        },
        'rejection_monitor': {
            'headline': '拒绝与时段表现',
            'slot_hints': slot.get('hints') or [],
            'recent_closed': closed,
            'win_rate': win_rate,
            'raw': slot,
        },
        'focus_review': {
            'headline': '边际诊断回顾',
            'success_count': recent_success,
            'fail_count': recent_fail,
            'raw': edge,
        },
    }


def can_use_legacy_bridge(*, username: str, bootstrap_username: str) -> bool:
    return bool(has_legacy_db() and username == bootstrap_username)
