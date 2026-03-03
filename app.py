import sys
import os
import sqlite3
import copy
import html
import re
import json
from flask import Flask, jsonify, render_template, request
import threading
import time
import datetime
import requests
import collections
import math
import uuid
import logging

# Ensure logs don't clutter terminal too much
log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR)

try:
    import akshare as ak
except ImportError:
    ak = None

app = Flask(__name__)

HEADERS = {'Referer': 'http://finance.sina.com.cn'}
MAX_STOCKS = 3
MARKET_CLOSE_MINUTE = 15 * 60
PRE_CLOSE_FLATTEN_MINUTE = 14 * 60 + 57
PRE_CLOSE_WARN_MINUTE = 14 * 60 + 50
PAPER_START_CASH = 800000.0

# === SQLite 持久化 ===
DB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data')
DB_PATH = os.path.join(DB_DIR, 'signals.db')
DEBUG_LOG_DIR = os.path.join(DB_DIR, 'debug_logs')
REPORT_DIR = os.path.join(DB_DIR, 'reports', 'daily')
TUNING_DIR = os.path.join(DB_DIR, 'reports', 'tuning')
BUNDLE_DIR = os.path.join(DB_DIR, 'reports', 'bundle')

debug_log_lock = threading.RLock()

STRATEGY_BOOL_KEYS = (
    'buy_require_confirmation', 'buy_reject_bearish_tape',
    'buy_auto_pause', 'close_pending_after_market',
    'debug_log_enabled', 'auto_daily_report_enabled',
    'time_slot_enabled', 'risk_guard_enabled',
    'regime_filter_enabled', 'regime_require_trend_alignment',
    'regime_block_open_close',
    'paper_trade_enabled', 'paper_auto_execute'
)
STRATEGY_FLOAT_KEYS = (
    'win_threshold', 'loss_threshold',
    'buy_min_score', 'sell_min_score', 'buy_pause_min_wr',
    'risk_daily_profit_floor', 'regime_target_wr', 'trade_cost_buffer',
    'paper_base_order_pct', 'paper_max_stock_pct', 'paper_slippage_pct',
    'paper_commission_rate', 'paper_sell_stamp_tax'
)
STRATEGY_INT_KEYS = (
    'buy_pause_window', 'buy_pause_min_samples',
    'risk_max_consecutive_fail', 'risk_pause_minutes',
    'regime_lookback_days', 'regime_min_samples', 'regime_slot_min_samples',
    'paper_min_lot'
)

DEFAULT_TIME_SLOT_TEMPLATES = {
    # 早盘前半小时噪声大，整体更保守
    'open': {'buy_min_score': 0.62, 'sell_min_score': 0.57, 'win_threshold': 0.011, 'loss_threshold': 0.007},
    # 上午中段恢复到常规
    'morning': {'buy_min_score': 0.58, 'sell_min_score': 0.55},
    # 午后开盘先观察，BUY 提高门槛
    'afternoon_open': {'buy_min_score': 0.60, 'sell_min_score': 0.56},
    # 午后中段常规
    'afternoon': {'buy_min_score': 0.58, 'sell_min_score': 0.55},
    # 尾盘减少逆势抄底
    'close': {'buy_min_score': 0.63, 'sell_min_score': 0.58, 'loss_threshold': 0.007}
}

UNIT_INTERVAL_FLOAT_KEYS = {
    'win_threshold', 'loss_threshold',
    'buy_min_score', 'sell_min_score', 'buy_pause_min_wr', 'regime_target_wr',
    'trade_cost_buffer', 'paper_base_order_pct', 'paper_max_stock_pct',
    'paper_slippage_pct', 'paper_commission_rate', 'paper_sell_stamp_tax'
}

SIGNED_FLOAT_KEYS = {
    'risk_daily_profit_floor'
}

def get_debug_log_path(target_date=None):
    day = target_date or datetime.datetime.now().strftime('%Y-%m-%d')
    os.makedirs(DEBUG_LOG_DIR, exist_ok=True)
    return os.path.join(DEBUG_LOG_DIR, f'{day}.jsonl')

def get_strategy_snapshot():
    """抽取策略关键参数，便于回放日志时对照当时配置。"""
    keys = STRATEGY_FLOAT_KEYS + STRATEGY_INT_KEYS + STRATEGY_BOOL_KEYS
    with state_lock:
        snapshot = {k: success_rates.get(k) for k in keys}
        snapshot['time_slot_templates'] = copy.deepcopy(success_rates.get('time_slot_templates', {}))
        return snapshot

def log_debug_event(event, payload=None, target_date=None):
    with state_lock:
        enabled = bool(success_rates.get('debug_log_enabled', True))
    if not enabled:
        return

    entry = {
        'ts': datetime.datetime.now().isoformat(timespec='seconds'),
        'event': event
    }
    if payload:
        entry.update(payload)

    path = get_debug_log_path(target_date)
    try:
        with debug_log_lock:
            with open(path, 'a', encoding='utf-8') as f:
                f.write(json.dumps(entry, ensure_ascii=False) + '\n')
    except Exception as e:
        print(f"debug log write error: {e}")

def to_bool(v):
    if isinstance(v, bool):
        return v
    if isinstance(v, str):
        return v.strip().lower() in ('1', 'true', 'yes', 'on')
    return bool(v)

def normalize_strategy_patch(patch):
    """把外部传入的策略参数标准化并做边界校验。"""
    normalized = {}
    errors = {}

    for key in STRATEGY_FLOAT_KEYS:
        if key not in patch:
            continue
        try:
            val = float(patch[key])
        except Exception:
            errors[key] = f'invalid float: {patch[key]}'
            continue
        if key not in SIGNED_FLOAT_KEYS and val < 0:
            errors[key] = 'must be >= 0'
            continue
        if key in SIGNED_FLOAT_KEYS and abs(val) > 100:
            errors[key] = 'must be between -100 and 100'
            continue
        # 这些字段都按比例处理，限制在 [0, 1] 以内
        if key in UNIT_INTERVAL_FLOAT_KEYS and val > 1:
            errors[key] = 'must be <= 1'
            continue
        normalized[key] = val

    for key in STRATEGY_INT_KEYS:
        if key not in patch:
            continue
        try:
            val = int(patch[key])
        except Exception:
            errors[key] = f'invalid int: {patch[key]}'
            continue
        if val <= 0:
            errors[key] = 'must be > 0'
            continue
        normalized[key] = val

    for key in STRATEGY_BOOL_KEYS:
        if key not in patch:
            continue
        normalized[key] = to_bool(patch[key])

    if 'time_slot_templates' in patch:
        tpl = patch['time_slot_templates']
        if not isinstance(tpl, dict):
            errors['time_slot_templates'] = 'must be object'
        else:
            clean_tpl = {}
            for slot, cfg in tpl.items():
                if not isinstance(cfg, dict):
                    errors[f'time_slot_templates.{slot}'] = 'must be object'
                    continue
                slot_cfg = {}
                for k, v in cfg.items():
                    if k in STRATEGY_FLOAT_KEYS:
                        try:
                            fv = float(v)
                        except Exception:
                            errors[f'time_slot_templates.{slot}.{k}'] = f'invalid float: {v}'
                            continue
                        if k not in SIGNED_FLOAT_KEYS and fv < 0:
                            errors[f'time_slot_templates.{slot}.{k}'] = 'must be >= 0'
                            continue
                        if k in SIGNED_FLOAT_KEYS and abs(fv) > 100:
                            errors[f'time_slot_templates.{slot}.{k}'] = 'must be between -100 and 100'
                            continue
                        if k in UNIT_INTERVAL_FLOAT_KEYS and fv > 1:
                            errors[f'time_slot_templates.{slot}.{k}'] = 'must be <= 1'
                            continue
                        slot_cfg[k] = fv
                    elif k in STRATEGY_INT_KEYS:
                        try:
                            iv = int(v)
                        except Exception:
                            errors[f'time_slot_templates.{slot}.{k}'] = f'invalid int: {v}'
                            continue
                        if iv <= 0:
                            errors[f'time_slot_templates.{slot}.{k}'] = 'must be > 0'
                            continue
                        slot_cfg[k] = iv
                    elif k in STRATEGY_BOOL_KEYS:
                        slot_cfg[k] = to_bool(v)
                    else:
                        errors[f'time_slot_templates.{slot}.{k}'] = 'unsupported key'
                clean_tpl[str(slot)] = slot_cfg
            normalized['time_slot_templates'] = clean_tpl

    return normalized, errors

def apply_strategy_patch(patch):
    """
    应用策略参数 patch。
    返回 (success, errors, applied_patch)。
    """
    normalized, errors = normalize_strategy_patch(patch)
    if errors:
        return False, errors, {}

    with state_lock:
        prev_window = int(success_rates.get('buy_pause_window', 20))
        for k, v in normalized.items():
            success_rates[k] = v
        # time slot 模板按整体覆盖，避免残留旧键
        if 'time_slot_templates' in normalized:
            success_rates['time_slot_templates'] = copy.deepcopy(normalized['time_slot_templates'])
        new_window = int(success_rates.get('buy_pause_window', prev_window))

        # 窗口变化后重建缓存
        if new_window != prev_window:
            for code in list(buy_outcomes.keys()):
                buy_outcomes[code] = load_recent_buy_outcomes(code, new_window)

    return True, {}, normalized

def save_param_version(note=''):
    snapshot = get_strategy_snapshot()
    conn = get_db()
    cur = conn.execute(
        'INSERT INTO param_versions (note, params_json) VALUES (?,?)',
        (str(note or ''), json.dumps(snapshot, ensure_ascii=False))
    )
    conn.commit()
    version_id = cur.lastrowid
    conn.close()
    return version_id, snapshot

def list_param_versions(limit=30):
    limit = max(1, min(int(limit), 500))
    conn = get_db()
    rows = conn.execute(
        'SELECT id, created_at, note, params_json FROM param_versions ORDER BY id DESC LIMIT ?',
        (limit,)
    ).fetchall()
    conn.close()
    items = []
    for r in rows:
        try:
            params = json.loads(r['params_json'])
        except Exception:
            params = {}
        items.append({
            'id': r['id'],
            'created_at': r['created_at'],
            'note': r['note'],
            'params': params
        })
    return items

def get_param_version(version_id):
    conn = get_db()
    row = conn.execute(
        'SELECT id, created_at, note, params_json FROM param_versions WHERE id=?',
        (version_id,)
    ).fetchone()
    conn.close()
    if not row:
        return None
    try:
        params = json.loads(row['params_json'])
    except Exception:
        params = {}
    return {
        'id': row['id'],
        'created_at': row['created_at'],
        'note': row['note'],
        'params': params
    }

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    os.makedirs(DB_DIR, exist_ok=True)
    conn = get_db()
    conn.execute('''
        CREATE TABLE IF NOT EXISTS signals (
            id TEXT PRIMARY KEY,
            date TEXT,
            time TEXT,
            seq_no INTEGER DEFAULT 0,
            code TEXT,
            name TEXT,
            type TEXT,
            level INTEGER,
            price REAL,
            desc TEXT,
            status TEXT DEFAULT 'pending',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            resolved_at TIMESTAMP
        )
    ''')
    alter_sqls = [
        'ALTER TABLE signals ADD COLUMN seq_no INTEGER DEFAULT 0',
        'ALTER TABLE signals ADD COLUMN resolved_price REAL DEFAULT 0.0',
        'ALTER TABLE signals ADD COLUMN gross_profit_pct REAL DEFAULT 0.0',
        'ALTER TABLE signals ADD COLUMN profit_pct REAL DEFAULT 0.0',
        'ALTER TABLE signals ADD COLUMN resolve_msg TEXT DEFAULT ""'
    ]
    for sql in alter_sqls:
        try:
            conn.execute(sql)
        except Exception:
            pass
    conn.execute('''
        CREATE TABLE IF NOT EXISTS daily_stats (
            date TEXT PRIMARY KEY,
            total INTEGER DEFAULT 0,
            success INTEGER DEFAULT 0,
            fail INTEGER DEFAULT 0,
            win_rate REAL DEFAULT 0
        )
    ''')
    conn.execute('''
        CREATE TABLE IF NOT EXISTS param_versions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            note TEXT DEFAULT '',
            params_json TEXT NOT NULL
        )
    ''')
    conn.execute('''
        CREATE TABLE IF NOT EXISTS paper_account (
            id INTEGER PRIMARY KEY CHECK (id=1),
            starting_cash REAL NOT NULL DEFAULT 800000.0,
            cash REAL NOT NULL DEFAULT 800000.0,
            realized_pnl REAL NOT NULL DEFAULT 0.0,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.execute('''
        CREATE TABLE IF NOT EXISTS paper_positions (
            code TEXT PRIMARY KEY,
            name TEXT DEFAULT '',
            total_qty INTEGER NOT NULL DEFAULT 0,
            available_qty INTEGER NOT NULL DEFAULT 0,
            today_buy_qty INTEGER NOT NULL DEFAULT 0,
            today_sell_qty INTEGER NOT NULL DEFAULT 0,
            avg_cost REAL NOT NULL DEFAULT 0.0,
            realized_pnl REAL NOT NULL DEFAULT 0.0,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.execute('''
        CREATE TABLE IF NOT EXISTS paper_orders (
            order_id TEXT PRIMARY KEY,
            signal_id TEXT DEFAULT '',
            date TEXT DEFAULT '',
            time TEXT DEFAULT '',
            code TEXT DEFAULT '',
            name TEXT DEFAULT '',
            side TEXT DEFAULT '',
            qty INTEGER NOT NULL DEFAULT 0,
            price REAL NOT NULL DEFAULT 0.0,
            amount REAL NOT NULL DEFAULT 0.0,
            fee REAL NOT NULL DEFAULT 0.0,
            status TEXT DEFAULT 'filled',
            reason TEXT DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.execute('CREATE INDEX IF NOT EXISTS idx_paper_orders_created ON paper_orders(created_at DESC)')
    conn.execute('''
        CREATE TABLE IF NOT EXISTS paper_meta (
            k TEXT PRIMARY KEY,
            v TEXT NOT NULL
        )
    ''')
    conn.execute('''
        CREATE TABLE IF NOT EXISTS paper_base_config (
            code TEXT PRIMARY KEY,
            name TEXT DEFAULT '',
            base_amount REAL NOT NULL DEFAULT 0.0,
            base_cost_line REAL NOT NULL DEFAULT 0.0,
            t_order_amount REAL NOT NULL DEFAULT 0.0,
            t_daily_budget REAL NOT NULL DEFAULT 0.0,
            t_costline_strength REAL NOT NULL DEFAULT 1.0,
            enabled INTEGER NOT NULL DEFAULT 1,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    base_alter_sqls = [
        'ALTER TABLE paper_base_config ADD COLUMN t_order_amount REAL NOT NULL DEFAULT 0.0',
        'ALTER TABLE paper_base_config ADD COLUMN t_daily_budget REAL NOT NULL DEFAULT 0.0',
        'ALTER TABLE paper_base_config ADD COLUMN t_costline_strength REAL NOT NULL DEFAULT 1.0'
    ]
    for sql in base_alter_sqls:
        try:
            conn.execute(sql)
        except Exception:
            pass
    conn.execute(
        'INSERT OR IGNORE INTO paper_account (id, starting_cash, cash, realized_pnl) VALUES (1, ?, ?, 0.0)',
        (PAPER_START_CASH, PAPER_START_CASH)
    )
    conn.execute(
        "INSERT OR IGNORE INTO paper_meta (k, v) VALUES ('trading_date', '')"
    )
    conn.commit()
    conn.close()
    print(f"💾 数据库已初始化: {DB_PATH}")

def rebuild_daily_stats():
    """根据信号明细重建 daily_stats，避免跨日平仓导致统计漂移。"""
    try:
        conn = get_db()
        rows = conn.execute(
            '''
            SELECT date,
                   COUNT(*) AS total,
                   SUM(CASE WHEN status='success' THEN 1 ELSE 0 END) AS success,
                   SUM(CASE WHEN status='fail' THEN 1 ELSE 0 END) AS fail
            FROM signals
            GROUP BY date
            '''
        ).fetchall()

        conn.execute('DELETE FROM daily_stats')
        for r in rows:
            total = int(r['total'] or 0)
            success = int(r['success'] or 0)
            fail = int(r['fail'] or 0)
            completed = success + fail
            win_rate = round(success * 100.0 / completed, 1) if completed > 0 else 0.0
            conn.execute(
                'INSERT INTO daily_stats (date, total, success, fail, win_rate) VALUES (?,?,?,?,?)',
                (r['date'], total, success, fail, win_rate)
            )
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"rebuild daily_stats error: {e}")

def db_save_signal(sig):
    try:
        conn = get_db()
        signal_date = sig.get('date') or datetime.datetime.now().strftime('%Y-%m-%d')
        conn.execute(
            'INSERT OR REPLACE INTO signals (id, date, time, seq_no, code, name, type, level, price, desc, status) VALUES (?,?,?,?,?,?,?,?,?,?,?)',
            (sig['id'], signal_date, sig.get('time',''), int(sig.get('seq_no') or 0), sig.get('code',''), sig.get('name',''),
             sig['type'], sig.get('level',0), sig['price'], sig.get('desc',''), sig.get('status','pending'))
        )
        # 更新当日统计
        conn.execute('INSERT OR IGNORE INTO daily_stats (date) VALUES (?)', (signal_date,))
        conn.execute('UPDATE daily_stats SET total = total + 1 WHERE date = ?', (signal_date,))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f'db save error: {e}')

def get_next_signal_seq(code, signal_date):
    conn = get_db()
    row = conn.execute(
        'SELECT COALESCE(MAX(seq_no), 0) AS m FROM signals WHERE code=? AND date=?',
        (code, signal_date)
    ).fetchone()
    conn.close()
    return int(row['m'] or 0) + 1

def db_resolve_signal(sig_id, status, resolved_price=0.0, gross_profit_pct=0.0, profit_pct=0.0, resolve_msg='', signal_date=None):
    try:
        conn = get_db()
        target_date = signal_date
        if not target_date:
            row = conn.execute('SELECT date FROM signals WHERE id=?', (sig_id,)).fetchone()
            target_date = row['date'] if row and row['date'] else datetime.datetime.now().strftime('%Y-%m-%d')

        conn.execute('INSERT OR IGNORE INTO daily_stats (date) VALUES (?)', (target_date,))
        conn.execute(
            'UPDATE signals SET status=?, resolved_at=CURRENT_TIMESTAMP, resolved_price=?, gross_profit_pct=?, profit_pct=?, resolve_msg=? WHERE id=?',
            (status, resolved_price, gross_profit_pct, profit_pct, resolve_msg, sig_id)
        )
        if status == 'success':
            conn.execute('UPDATE daily_stats SET success = success + 1 WHERE date = ?', (target_date,))
        elif status == 'fail':
            conn.execute('UPDATE daily_stats SET fail = fail + 1 WHERE date = ?', (target_date,))
        # 更新胜率
        conn.execute(
            'UPDATE daily_stats SET win_rate = CASE WHEN (success+fail)>0 THEN ROUND(success*100.0/(success+fail),1) ELSE 0 END WHERE date = ?',
            (target_date,)
        )
        conn.commit()
        conn.close()
        with state_lock:
            quality_cache.clear()
    except Exception as e:
        print(f'db resolve error: {e}')

def load_today_signals():
    """启动时恢复今日信号记录"""
    try:
        conn = get_db()
        today = datetime.datetime.now().strftime('%Y-%m-%d')
        rows = conn.execute('SELECT * FROM signals WHERE date=? ORDER BY created_at DESC', (today,)).fetchall()
        conn.close()
        restored = []
        for r in rows:
            sig = {'id': r['id'], 'date': r['date'], 'time': r['time'], 'seq_no': r['seq_no'] if 'seq_no' in r.keys() else 0, 'code': r['code'], 'name': r['name'],
                   'type': r['type'], 'level': r['level'], 'price': r['price'],
                   'desc': r['desc'], 'status': r['status'],
                   'resolved_price': r['resolved_price'] if 'resolved_price' in r.keys() else 0.0,
                   'gross_profit_pct': r['gross_profit_pct'] if 'gross_profit_pct' in r.keys() else (r['profit_pct'] if 'profit_pct' in r.keys() else 0.0),
                   'profit_pct': r['profit_pct'] if 'profit_pct' in r.keys() else 0.0,
                   'resolve_msg': r['resolve_msg'] if 'resolve_msg' in r.keys() else ''}
            restored.append(sig)
        return restored
    except:
        return []

init_db()
rebuild_daily_stats()

# === 全局状态 =========================
active_stocks = {}  # {'sh600079': '人福医药'}
market_data = {}    # {'sh600079': [{time, price, vwap}...]}
analyzers = {}      # {'sh600079': DayTradeAnalyzer()}
signals_history = []# 所有股票的信号流
pending_signals = []# 正在等待出止盈/止损的信号
success_rates = {
    'total': 0, 'success': 0, 'fail': 0, 'flat': 0, 'pending': 0,
    'win_threshold': 0.010, 'loss_threshold': 0.008,
    # BUY/SELL 分离过滤参数（默认对 BUY 更严格）
    'buy_min_score': 0.58, 'sell_min_score': 0.55,
    'buy_require_confirmation': True, 'buy_reject_bearish_tape': True,
    # BUY 自动降噪：近 N 笔胜率过低则临时暂停 BUY
    'buy_auto_pause': True, 'buy_pause_window': 20,
    'buy_pause_min_samples': 10, 'buy_pause_min_wr': 0.35,
    # 收盘后是否强制平掉未完成信号
    'close_pending_after_market': True,
    # 分时段参数模板
    'time_slot_enabled': True,
    'time_slot_templates': copy.deepcopy(DEFAULT_TIME_SLOT_TEMPLATES),
    # 风控总闸（回撤/连败）
    'risk_guard_enabled': True,
    'risk_max_consecutive_fail': 4,
    'risk_daily_profit_floor': -2.0,
    'risk_pause_minutes': 30,
    # 成本缓冲（净收益判断）：毛收益需超过该比例才记为 success
    'trade_cost_buffer': 0.0012,
    # 模拟交易（80w 起步）执行参数
    'paper_trade_enabled': True,
    'paper_auto_execute': True,
    'paper_base_order_pct': 0.10,
    'paper_max_stock_pct': 0.35,
    'paper_slippage_pct': 0.0002,
    'paper_commission_rate': 0.0003,
    'paper_sell_stamp_tax': 0.001,
    'paper_min_lot': 100,
    # 仅在高质量策略窗口开仓，目标胜率保守设为 75%
    'regime_filter_enabled': True,
    'regime_target_wr': 0.75,
    'regime_lookback_days': 10,
    'regime_min_samples': 20,
    'regime_slot_min_samples': 5,
    'regime_require_trend_alignment': True,
    'regime_block_open_close': True,
    # 调试日志开关（结构化 JSONL）
    'debug_log_enabled': True,
    # 收盘后自动生成日报
    'auto_daily_report_enabled': True,
    'stocks': {}
}
last_signal_time = {} # code -> timestamp
stock_contexts = {} # code -> { 'trend': '', 'industry': '', 'news': [] }
stock_extras = {}   # code -> { 'yest_close': float, 'open_price': float }
global_market = { 'indices': [], 'update_time': '' }
last_context_refresh = 0 # timestamp
state_lock = threading.RLock()
buy_outcomes = {}   # code -> deque([1/0], maxlen=pause_window)
last_auto_report_date = ''
risk_state = {
    'day': '',
    'consecutive_fail': 0,
    'daily_profit_pct': 0.0,
    'paused_until_ts': 0.0,
    'pause_reason': '',
    'trigger_count': 0
}
health_state = {
    'worker_started_at': datetime.datetime.now().isoformat(timespec='seconds'),
    'last_loop_ts': 0.0,
    'last_fetch_ok_ts': 0.0,
    'last_fetch_latency_ms': 0.0,
    'request_errors': 0,
    'parse_errors': 0,
    'worker_errors': 0,
    'last_error': '',
    'last_tick_by_code': {},
    'stale_seconds_by_code': {},
    'alerts': []
}
quality_cache = {}  # key -> {'ts': float, 'value': {...}}

def is_trading_time():
    """A股交易时段检测：工作日 9:30-11:30, 13:00-15:00"""
    now = datetime.datetime.now()
    if now.weekday() >= 5:  # 周末
        return False
    t = now.hour * 60 + now.minute
    return (9*60+30 <= t <= 11*60+30) or (13*60 <= t <= MARKET_CLOSE_MINUTE)

def is_pre_close_window(now=None):
    dt = now or datetime.datetime.now()
    if dt.weekday() >= 5:
        return False
    m = dt.hour * 60 + dt.minute
    return PRE_CLOSE_FLATTEN_MINUTE <= m <= MARKET_CLOSE_MINUTE

def build_pre_close_alert_snapshot(pending_list, current_state, now=None):
    """
    构建尾盘提醒：
    - 14:50-14:56：提醒手动关注待平仓单
    - 14:57-15:00：进入系统强平窗口
    """
    dt = now or datetime.datetime.now()
    today = dt.strftime('%Y-%m-%d')
    if dt.weekday() >= 5:
        return {
            'enabled': False,
            'stage': 'off',
            'msg': '非交易日',
            'minutes_to_close': None,
            'alert_items': []
        }

    minute = dt.hour * 60 + dt.minute
    minutes_to_close = MARKET_CLOSE_MINUTE - minute
    if minute < PRE_CLOSE_WARN_MINUTE:
        stage = 'normal'
    elif minute < PRE_CLOSE_FLATTEN_MINUTE:
        stage = 'warn'
    elif minute <= MARKET_CLOSE_MINUTE:
        stage = 'force'
    else:
        stage = 'closed'

    alert_items = []
    for sig in pending_list:
        if str(sig.get('date', '')) != today:
            continue
        code = str(sig.get('code', ''))
        current_price = float(current_state.get(code, {}).get('price', sig.get('price', 0.0)) or 0.0)
        entry_price = float(sig.get('price', 0.0) or 0.0)
        sig_type = str(sig.get('type', ''))
        win_price = float(sig.get('win_price', 0.0) or 0.0)
        stop_price = float(sig.get('stop_price', 0.0) or 0.0)

        # 若动态止盈止损尚未初始化，则用策略默认阈值兜底。
        if entry_price > 0 and (win_price <= 0 or stop_price <= 0):
            with state_lock:
                win_threshold = float(success_rates.get('win_threshold', 0.010))
                loss_threshold = float(success_rates.get('loss_threshold', 0.008))
            if sig_type == 'BUY':
                win_price = entry_price * (1 + win_threshold)
                stop_price = entry_price * (1 - loss_threshold)
            else:
                win_price = entry_price * (1 - win_threshold)
                stop_price = entry_price * (1 + loss_threshold)

        if sig_type == 'BUY':
            hit_win = current_price >= win_price if win_price > 0 else False
            hit_stop = current_price <= stop_price if stop_price > 0 else False
        else:
            hit_win = current_price <= win_price if win_price > 0 else False
            hit_stop = current_price >= stop_price if stop_price > 0 else False

        gross_return, net_return, predicted = classify_trade_result(sig_type, entry_price, current_price)
        should_flatten = (stage in ('warn', 'force')) and (not hit_win) and (not hit_stop)
        alert_items.append({
            'signal_id': sig.get('id'),
            'seq_no': int(sig.get('seq_no') or 0),
            'code': code,
            'name': sig.get('name', ''),
            'type': sig_type,
            'time': sig.get('time', ''),
            'entry_price': entry_price,
            'current_price': current_price,
            'win_price': win_price,
            'stop_price': stop_price,
            'hit_win': hit_win,
            'hit_stop': hit_stop,
            'should_flatten': should_flatten,
            'gross_profit_pct': round(gross_return * 100, 4),
            'net_profit_pct': round(net_return * 100, 4),
            'predicted_result': predicted
        })

    alert_items.sort(
        key=lambda x: (
            0 if x.get('should_flatten') else 1,
            abs(float(x.get('net_profit_pct', 0.0)))
        ),
        reverse=False
    )

    if stage == 'warn':
        msg = f'距离收盘约 {max(0, minutes_to_close)} 分钟，优先处理未触发止盈止损的挂单'
    elif stage == 'force':
        msg = f'已进入强平窗口（{max(0, minutes_to_close)} 分钟内收盘）'
    elif stage == 'closed':
        msg = '已收盘'
    else:
        msg = '盘中正常监控'

    return {
        'enabled': stage in ('warn', 'force'),
        'stage': stage,
        'msg': msg,
        'minutes_to_close': max(0, minutes_to_close) if stage != 'off' else None,
        'pending_count': len(alert_items),
        'need_flatten_count': sum(1 for x in alert_items if x.get('should_flatten')),
        'alert_items': alert_items
    }

def paper_rollover_if_new_day(now=None):
    """交易日切换时，把持仓可卖数量重置为 total_qty（模拟 T+1 解锁）。"""
    dt = now or datetime.datetime.now()
    today = dt.strftime('%Y-%m-%d')
    conn = get_db()
    row = conn.execute("SELECT v FROM paper_meta WHERE k='trading_date'").fetchone()
    last_day = row['v'] if row else ''
    changed = (last_day != today)
    if changed:
        conn.execute(
            '''
            UPDATE paper_positions
            SET available_qty = total_qty,
                today_buy_qty = 0,
                today_sell_qty = 0,
                updated_at = CURRENT_TIMESTAMP
            '''
        )
        conn.execute(
            "INSERT OR REPLACE INTO paper_meta (k, v) VALUES ('trading_date', ?)",
            (today,)
        )
        conn.commit()
    conn.close()
    if changed:
        log_debug_event('paper_rollover', {'date': today})

def calc_paper_order_fee(side, amount, commission_rate, sell_stamp_tax):
    commission = max(5.0, amount * commission_rate)
    stamp = amount * sell_stamp_tax if side == 'SELL' else 0.0
    return commission + stamp

def round_lot_qty(raw_qty, lot_size):
    lot = max(1, int(lot_size))
    if raw_qty <= 0:
        return 0
    return int(raw_qty // lot) * lot

def get_trend_multiplier(side, trend_text):
    txt = str(trend_text or '')
    if side == 'BUY':
        if '多头' in txt:
            return 1.2
        if '空头' in txt:
            return 0.6
        return 1.0
    # SELL 作为做T减仓：空头更积极，多头更保守
    if '空头' in txt:
        return 1.3
    if '多头' in txt:
        return 0.7
    return 1.0

def calc_base_target_qty(base_amount, base_cost_line, lot_size):
    amount = float(base_amount or 0.0)
    cost_line = float(base_cost_line or 0.0)
    if amount <= 0 or cost_line <= 0:
        return 0
    return round_lot_qty(amount / cost_line, lot_size)

def resolve_t_daily_budget(base_amount, t_daily_budget, fallback_budget=0.0):
    """
    解析单票日内T额度：
    1) 未配置时默认使用底仓金额；
    2) 配置值超过底仓时按底仓封顶；
    3) 无底仓时回退到 fallback_budget（如按账户净值估算）。
    """
    base_amt = max(0.0, float(base_amount or 0.0))
    day_budget = max(0.0, float(t_daily_budget or 0.0))

    if day_budget <= 0 and base_amt > 0:
        day_budget = base_amt
    if base_amt > 0 and day_budget > base_amt:
        day_budget = base_amt
    if day_budget <= 0:
        day_budget = max(0.0, float(fallback_budget or 0.0))
    return day_budget

def calc_t_order_caps(t_daily_budget, t_order_amount, used_count):
    """
    根据“单笔T金额 + 每日T额度”推导最大可做T次数。
    - t_order_amount<=0: 不按次数限制；
    - 否则 max_orders=floor(daily_budget / order_amount)。
    """
    order_amt = max(0.0, float(t_order_amount or 0.0))
    day_budget = max(0.0, float(t_daily_budget or 0.0))
    used = max(0, int(used_count or 0))
    max_orders = int(day_budget // order_amt) if order_amt > 0 else 0
    remaining_orders = max(0, max_orders - used) if max_orders > 0 else 0
    return max_orders, remaining_orders

def get_today_t_usage(code, trade_date):
    conn = get_db()
    row = conn.execute(
        '''
        SELECT
            COALESCE(SUM(amount), 0.0) AS used_amount,
            COUNT(*) AS used_count
        FROM paper_orders
        WHERE code=?
          AND date=?
          AND status='filled'
          AND reason LIKE 't_%'
        ''',
        (str(code), str(trade_date))
    ).fetchone()
    conn.close()
    return float(row['used_amount'] or 0.0), int(row['used_count'] or 0)

def calc_effective_cost_line_from_pos(base_cfg, pos_row, lot_size):
    if not base_cfg:
        return 0.0
    if not base_cfg.get('enabled'):
        return 0.0
    base_amount = float(base_cfg.get('base_amount', 0.0))
    base_cost_line = float(base_cfg.get('base_cost_line', 0.0))
    if base_amount <= 0 or base_cost_line <= 0:
        return 0.0
    base_qty = calc_base_target_qty(base_amount, base_cost_line, lot_size)
    if base_qty <= 0:
        return 0.0
    realized = float((pos_row['realized_pnl'] if pos_row else 0.0) or 0.0)
    return max(0.0, base_cost_line - realized / base_qty)

def get_base_config_map(conn=None):
    close_conn = False
    if conn is None:
        conn = get_db()
        close_conn = True
    rows = conn.execute(
        '''
        SELECT code, name, base_amount, base_cost_line, t_order_amount, t_daily_budget, t_costline_strength, enabled, updated_at
        FROM paper_base_config
        '''
    ).fetchall()
    if close_conn:
        conn.close()
    mapping = {}
    for r in rows:
        mapping[str(r['code'])] = {
            'code': r['code'],
            'name': r['name'],
            'base_amount': float(r['base_amount'] or 0.0),
            'base_cost_line': float(r['base_cost_line'] or 0.0),
            't_order_amount': float(r['t_order_amount'] or 0.0),
            't_daily_budget': float(r['t_daily_budget'] or 0.0),
            't_costline_strength': float(r['t_costline_strength'] or 1.0),
            'enabled': bool(int(r['enabled'] or 0)),
            'updated_at': r['updated_at']
        }
    return mapping

def list_base_configs():
    return list(get_base_config_map().values())

def upsert_base_config(code, name, base_amount, base_cost_line, enabled=True, t_order_amount=0.0, t_daily_budget=0.0, t_costline_strength=1.0):
    c = str(code or '').strip().lower()
    if not c:
        return False, 'missing code'
    try:
        amt = float(base_amount or 0.0)
        cost = float(base_cost_line or 0.0)
        ord_amt = float(t_order_amount or 0.0)
        day_budget = float(t_daily_budget or 0.0)
        strength = float(t_costline_strength or 1.0)
    except Exception:
        return False, 'invalid numeric fields'
    if amt < 0 or cost < 0 or ord_amt < 0 or day_budget < 0:
        return False, 'amount/cost/budget must be >= 0'
    if strength <= 0:
        return False, 't_costline_strength must be > 0'
    day_budget = resolve_t_daily_budget(amt, day_budget, fallback_budget=0.0)
    if day_budget > 0 and ord_amt > day_budget:
        ord_amt = day_budget
    conn = get_db()
    existing = conn.execute('SELECT name FROM paper_base_config WHERE code=?', (c,)).fetchone()
    final_name = str(name or '').strip()
    if not final_name and existing:
        final_name = str(existing['name'] or '')
    if not final_name:
        with state_lock:
            final_name = str(active_stocks.get(c, ''))
    conn.execute(
        '''
        INSERT OR REPLACE INTO paper_base_config
        (code, name, base_amount, base_cost_line, t_order_amount, t_daily_budget, t_costline_strength, enabled, updated_at)
        VALUES (?,?,?,?,?,?,?,?,CURRENT_TIMESTAMP)
        ''',
        (c, final_name, amt, cost, ord_amt, day_budget, strength, 1 if enabled else 0)
    )
    conn.commit()
    conn.close()
    return True, ''

def seed_base_positions(reseed=False):
    """
    将“底仓配置”写入模拟账户：
    - reseed=True: 清空现有仓位和订单，再按底仓重建
    - reseed=False: 仅在无仓位时补齐底仓
    """
    with state_lock:
        min_lot = int(success_rates.get('paper_min_lot', 100))

    conn = get_db()
    account = conn.execute('SELECT * FROM paper_account WHERE id=1').fetchone()
    if not account:
        conn.execute(
            'INSERT OR REPLACE INTO paper_account (id, starting_cash, cash, realized_pnl) VALUES (1, ?, ?, 0.0)',
            (PAPER_START_CASH, PAPER_START_CASH)
        )
        conn.commit()
        account = conn.execute('SELECT * FROM paper_account WHERE id=1').fetchone()

    if reseed:
        conn.execute('DELETE FROM paper_orders')
        conn.execute('DELETE FROM paper_positions')
        conn.execute(
            'UPDATE paper_account SET cash=starting_cash, realized_pnl=0.0, updated_at=CURRENT_TIMESTAMP WHERE id=1'
        )
        account = conn.execute('SELECT * FROM paper_account WHERE id=1').fetchone()

    cash = float(account['cash'] or 0.0)
    cfg_map = get_base_config_map(conn)
    applied = []

    for code, cfg in cfg_map.items():
        if not cfg.get('enabled'):
            continue
        target_qty = calc_base_target_qty(cfg.get('base_amount', 0.0), cfg.get('base_cost_line', 0.0), min_lot)
        if target_qty <= 0:
            continue
        base_cost = float(cfg.get('base_cost_line') or 0.0)
        need_cash = target_qty * base_cost
        if need_cash > cash + 1e-6:
            continue

        existing = conn.execute('SELECT total_qty FROM paper_positions WHERE code=?', (code,)).fetchone()
        if existing and int(existing['total_qty'] or 0) > 0 and not reseed:
            continue

        cash -= need_cash
        conn.execute(
            '''
            INSERT OR REPLACE INTO paper_positions
            (code, name, total_qty, available_qty, today_buy_qty, today_sell_qty, avg_cost, realized_pnl, updated_at)
            VALUES (?,?,?,?,?,?,?,0.0,CURRENT_TIMESTAMP)
            ''',
            (code, cfg.get('name', ''), target_qty, target_qty, 0, 0, base_cost)
        )
        oid = str(uuid.uuid4())
        today = datetime.datetime.now().strftime('%Y-%m-%d')
        now_t = datetime.datetime.now().strftime('%H:%M:%S')
        conn.execute(
            '''
            INSERT OR REPLACE INTO paper_orders
            (order_id, signal_id, date, time, code, name, side, qty, price, amount, fee, status, reason, created_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,CURRENT_TIMESTAMP)
            ''',
            (
                oid, '', today, now_t, code, cfg.get('name', ''), 'BUY', target_qty, base_cost,
                round(need_cash, 2), 0.0, 'filled', 'base_seed'
            )
        )
        applied.append({'code': code, 'name': cfg.get('name', ''), 'qty': target_qty, 'cost_line': base_cost})

    conn.execute(
        'UPDATE paper_account SET cash=?, updated_at=CURRENT_TIMESTAMP WHERE id=1',
        (cash,)
    )
    conn.commit()
    conn.close()
    if applied:
        log_debug_event('paper_base_seed_applied', {'count': len(applied), 'items': applied, 'reseed': bool(reseed)})
    return applied

def plan_paper_order(sig, market_price, account_row, pos_row, nav_approx):
    side = str(sig.get('type', ''))
    code = str(sig.get('code', ''))
    name = str(sig.get('name', ''))
    signal_id = str(sig.get('id', ''))
    sig_date = str(sig.get('date') or datetime.datetime.now().strftime('%Y-%m-%d'))
    sig_time = str(sig.get('time') or '')

    if side not in ('BUY', 'SELL'):
        return {'ok': False, 'reason': 'unsupported_side', 'order': None}
    base_price = float(market_price or sig.get('price') or 0.0)
    if base_price <= 0:
        return {'ok': False, 'reason': 'invalid_price', 'order': None}

    with state_lock:
        enabled = bool(success_rates.get('paper_trade_enabled', True))
        auto_exec = bool(success_rates.get('paper_auto_execute', True))
        base_pct = float(success_rates.get('paper_base_order_pct', 0.10))
        max_stock_pct = float(success_rates.get('paper_max_stock_pct', 0.35))
        slippage_pct = float(success_rates.get('paper_slippage_pct', 0.0002))
        min_lot = int(success_rates.get('paper_min_lot', 100))
        commission_rate = float(success_rates.get('paper_commission_rate', 0.0003))
        sell_stamp_tax = float(success_rates.get('paper_sell_stamp_tax', 0.001))
        trend_text = str(stock_contexts.get(code, {}).get('trend', ''))

    if not enabled or not auto_exec:
        return {'ok': False, 'reason': 'paper_disabled', 'order': None}

    trend_mul = get_trend_multiplier(side, trend_text)
    if int(sig.get('level') or 0) >= 2:
        trend_mul *= 1.2

    exec_price = base_price * (1 + slippage_pct) if side == 'BUY' else base_price * (1 - slippage_pct)
    exec_price = max(0.01, exec_price)

    cash = float(account_row['cash'] or 0.0)
    pos_total = int(pos_row['total_qty']) if pos_row else 0
    pos_available = int(pos_row['available_qty']) if pos_row else 0
    pos_realized = float((pos_row['realized_pnl'] if pos_row else 0.0) or 0.0)
    base_cfg = get_base_config_map().get(code, {})
    base_qty = 0
    if base_cfg and base_cfg.get('enabled'):
        base_qty = calc_base_target_qty(base_cfg.get('base_amount', 0.0), base_cfg.get('base_cost_line', 0.0), min_lot)
    base_amount = float(base_cfg.get('base_amount', 0.0)) if base_cfg else 0.0
    t_order_amount = float(base_cfg.get('t_order_amount', 0.0)) if base_cfg else 0.0
    t_daily_budget = float(base_cfg.get('t_daily_budget', 0.0)) if base_cfg else 0.0
    t_costline_strength = float(base_cfg.get('t_costline_strength', 1.0)) if base_cfg else 1.0
    t_costline_strength = max(0.1, t_costline_strength)
    t_daily_budget = resolve_t_daily_budget(base_amount, t_daily_budget, fallback_budget=nav_approx * max_stock_pct)
    used_amount, used_count = get_today_t_usage(code, sig_date)
    remaining_budget = max(0.0, t_daily_budget - used_amount)
    max_orders, remaining_orders = calc_t_order_caps(t_daily_budget, t_order_amount, used_count)
    effective_cost_line = calc_effective_cost_line_from_pos(base_cfg, pos_row, min_lot)

    target_budget = t_order_amount if t_order_amount > 0 else max(0.0, nav_approx * base_pct)
    target_budget *= trend_mul
    reason = 't_buy' if side == 'BUY' else 't_sell'
    if side == 'BUY' and pos_total < base_qty:
        reason = 't_buy_replenish'
        need_budget = max(0.0, (base_qty - pos_total) * exec_price)
        if t_order_amount <= 0:
            target_budget = max(target_budget, min(need_budget, t_daily_budget))
        else:
            target_budget = min(max(target_budget, need_budget), max(t_order_amount, need_budget))

    # 围绕成本线做 T：低于成本线偏买，高于成本线偏卖。
    if effective_cost_line > 0:
        dev = (effective_cost_line - exec_price) / effective_cost_line
        cost_mul = 1.0
        if side == 'BUY':
            if dev > 0:
                cost_mul = 1.0 + min(1.5, dev * 6.0 * t_costline_strength)
            else:
                cost_mul = max(0.4, 1.0 - min(0.6, abs(dev) * 3.0 * t_costline_strength))
        else:
            if dev < 0:
                cost_mul = 1.0 + min(1.5, abs(dev) * 6.0 * t_costline_strength)
            else:
                cost_mul = max(0.4, 1.0 - min(0.6, abs(dev) * 3.0 * t_costline_strength))
        target_budget *= cost_mul
        if abs(dev) >= 0.003:
            reason = reason + '_costline'

    qty = 0
    reject_reason = ''
    budget = min(target_budget, remaining_budget)
    if max_orders > 0 and used_count >= max_orders:
        reject_reason = 't_daily_order_limit_reached'
    elif budget < exec_price * min_lot:
        reject_reason = 't_daily_budget_exceeded'
    elif side == 'BUY':
        cur_exposure = pos_total * exec_price
        max_stock_budget = max(0.0, nav_approx * max_stock_pct - cur_exposure)
        budget = min(budget, max_stock_budget, cash)
        qty = round_lot_qty(budget / exec_price, min_lot)
        if qty < min_lot:
            reject_reason = 'insufficient_cash_or_position_limit'
    else:
        sellable_qty = round_lot_qty(max(0, pos_available), min_lot)
        if sellable_qty < min_lot:
            reject_reason = 'no_available_qty'
        else:
            qty = round_lot_qty(budget / exec_price, min_lot)
            qty = min(qty, sellable_qty)
            if qty < min_lot:
                reject_reason = 'available_qty_too_small' if budget >= exec_price * min_lot else 't_daily_budget_exceeded'

    amount = qty * exec_price
    fee = calc_paper_order_fee(side, amount, commission_rate, sell_stamp_tax) if qty > 0 else 0.0
    status = 'filled' if qty > 0 else 'rejected'
    final_reason = reason if qty > 0 else reject_reason
    order = {
        'order_id': str(uuid.uuid4()),
        'signal_id': signal_id,
        'date': sig_date,
        'time': sig_time,
        'code': code,
        'name': name,
        'side': side,
        'qty': int(qty),
        'price': round(exec_price, 4),
        'amount': round(amount, 2),
        'fee': round(fee, 2),
        'status': status,
        'reason': final_reason,
        'trend': trend_text,
        'base_qty': int(base_qty),
        'base_amount': round(base_amount, 2),
        'effective_cost_line': round(effective_cost_line, 4),
        't_order_amount': round(t_order_amount, 2),
        't_daily_budget': round(t_daily_budget, 2),
        't_used_amount': round(used_amount, 2),
        't_max_orders': int(max_orders),
        't_remaining_orders': int(remaining_orders),
        't_remaining_before': round(remaining_budget, 2),
        't_remaining_after': round(max(0.0, remaining_budget - amount), 2),
        't_used_count': int(used_count)
    }
    return {'ok': qty > 0, 'reason': final_reason, 'order': order}

def execute_paper_order(order):
    conn = get_db()
    account = conn.execute('SELECT * FROM paper_account WHERE id=1').fetchone()
    if not account:
        conn.execute(
            'INSERT OR REPLACE INTO paper_account (id, starting_cash, cash, realized_pnl) VALUES (1, ?, ?, 0.0)',
            (PAPER_START_CASH, PAPER_START_CASH)
        )
        conn.commit()
        account = conn.execute('SELECT * FROM paper_account WHERE id=1').fetchone()

    cash = float(account['cash'] or 0.0)
    realized_total = float(account['realized_pnl'] or 0.0)
    code = order['code']
    pos = conn.execute('SELECT * FROM paper_positions WHERE code=?', (code,)).fetchone()
    total_qty = int(pos['total_qty']) if pos else 0
    available_qty = int(pos['available_qty']) if pos else 0
    today_buy_qty = int(pos['today_buy_qty']) if pos else 0
    today_sell_qty = int(pos['today_sell_qty']) if pos else 0
    avg_cost = float(pos['avg_cost']) if pos else 0.0
    pos_realized = float(pos['realized_pnl']) if pos else 0.0

    side = order['side']
    qty = int(order['qty'])
    price = float(order['price'])
    amount = float(order['amount'])
    fee = float(order['fee'])
    status = order['status']
    reason = order.get('reason', '')
    realized_delta = 0.0

    if status == 'filled' and qty > 0:
        if side == 'BUY':
            total_cost = amount + fee
            if total_cost > cash + 1e-6:
                status = 'rejected'
                reason = 'cash_not_enough_at_execution'
            else:
                cash -= total_cost
                new_total = total_qty + qty
                avg_cost = ((avg_cost * total_qty) + total_cost) / new_total if new_total > 0 else 0.0
                total_qty = new_total
                today_buy_qty += qty
                # 当日买入不能卖，available_qty 保持不变
        else:
            if qty > available_qty:
                status = 'rejected'
                reason = 'available_qty_not_enough'
            else:
                proceeds = amount - fee
                cash += proceeds
                realized_delta = proceeds - (avg_cost * qty)
                total_qty -= qty
                available_qty -= qty
                today_sell_qty += qty
                pos_realized += realized_delta
                realized_total += realized_delta
                if total_qty <= 0:
                    total_qty = 0
                    available_qty = 0
                    avg_cost = 0.0

    conn.execute(
        '''
        INSERT OR REPLACE INTO paper_orders
        (order_id, signal_id, date, time, code, name, side, qty, price, amount, fee, status, reason)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
        ''',
        (
            order['order_id'], order.get('signal_id', ''), order.get('date', ''), order.get('time', ''),
            code, order.get('name', ''), side, qty, price, amount, fee, status, reason
        )
    )

    if total_qty > 0:
        conn.execute(
            '''
            INSERT OR REPLACE INTO paper_positions
            (code, name, total_qty, available_qty, today_buy_qty, today_sell_qty, avg_cost, realized_pnl, updated_at)
            VALUES (?,?,?,?,?,?,?,?,CURRENT_TIMESTAMP)
            ''',
            (code, order.get('name', ''), total_qty, available_qty, today_buy_qty, today_sell_qty, avg_cost, pos_realized)
        )
    else:
        conn.execute('DELETE FROM paper_positions WHERE code=?', (code,))

    conn.execute(
        'UPDATE paper_account SET cash=?, realized_pnl=?, updated_at=CURRENT_TIMESTAMP WHERE id=1',
        (cash, realized_total)
    )
    conn.commit()
    conn.close()

    result = dict(order)
    result['status'] = status
    result['reason'] = reason
    result['realized_delta'] = round(realized_delta, 2)
    result['cash_after'] = round(cash, 2)
    return result

def maybe_execute_paper_trade(sig, market_price):
    """信号落地后执行模拟交易（若开启）。"""
    paper_rollover_if_new_day()
    conn = get_db()
    account = conn.execute('SELECT * FROM paper_account WHERE id=1').fetchone()
    if not account:
        conn.execute(
            'INSERT OR REPLACE INTO paper_account (id, starting_cash, cash, realized_pnl) VALUES (1, ?, ?, 0.0)',
            (PAPER_START_CASH, PAPER_START_CASH)
        )
        conn.commit()
        account = conn.execute('SELECT * FROM paper_account WHERE id=1').fetchone()

    pos = conn.execute('SELECT * FROM paper_positions WHERE code=?', (sig.get('code', ''),)).fetchone()
    all_pos = conn.execute('SELECT total_qty, avg_cost FROM paper_positions').fetchall()
    conn.close()
    nav_approx = float(account['cash'] or 0.0) + sum(float(r['total_qty'] or 0) * float(r['avg_cost'] or 0.0) for r in all_pos)
    nav_approx = max(1.0, nav_approx)

    plan = plan_paper_order(sig, market_price, account, pos, nav_approx)
    order = plan.get('order')
    if not order:
        return {'executed': False, 'status': 'skipped', 'reason': plan.get('reason', 'no_order')}

    result = execute_paper_order(order)
    if result.get('status') == 'filled':
        log_debug_event(
            'paper_order_filled',
            {
                'signal_id': sig.get('id', ''),
                'code': sig.get('code', ''),
                'name': sig.get('name', ''),
                'side': result.get('side'),
                'qty': result.get('qty'),
                'price': result.get('price'),
                'amount': result.get('amount'),
                'fee': result.get('fee'),
                'realized_delta': result.get('realized_delta'),
                'reason': result.get('reason', '')
            },
            target_date=sig.get('date')
        )
        return {'executed': True, 'status': 'filled', 'order': result}

    log_debug_event(
        'paper_order_rejected',
        {
            'signal_id': sig.get('id', ''),
            'code': sig.get('code', ''),
            'name': sig.get('name', ''),
            'side': result.get('side'),
            'qty': result.get('qty'),
            'reason': result.get('reason', '')
        },
        target_date=sig.get('date')
    )
    return {'executed': False, 'status': result.get('status', 'rejected'), 'order': result}

def get_paper_snapshot(current_state=None, recent_limit=30):
    current_state = current_state or {}
    paper_rollover_if_new_day()
    trade_date = datetime.datetime.now().strftime('%Y-%m-%d')
    conn = get_db()
    account = conn.execute('SELECT * FROM paper_account WHERE id=1').fetchone()
    if not account:
        conn.execute(
            'INSERT OR REPLACE INTO paper_account (id, starting_cash, cash, realized_pnl) VALUES (1, ?, ?, 0.0)',
            (PAPER_START_CASH, PAPER_START_CASH)
        )
        conn.commit()
        account = conn.execute('SELECT * FROM paper_account WHERE id=1').fetchone()

    pos_rows = conn.execute(
        '''
        SELECT code, name, total_qty, available_qty, today_buy_qty, today_sell_qty, avg_cost, realized_pnl, updated_at
        FROM paper_positions
        ORDER BY code ASC
        '''
    ).fetchall()
    order_rows = conn.execute(
        '''
        SELECT order_id, signal_id, date, time, code, name, side, qty, price, amount, fee, status, reason, created_at
        FROM paper_orders
        ORDER BY created_at DESC
        LIMIT ?
        ''',
        (max(1, min(int(recent_limit), 200)),)
    ).fetchall()
    usage_rows = conn.execute(
        '''
        SELECT code, COALESCE(SUM(amount), 0.0) AS used_amount, COUNT(*) AS used_count
        FROM paper_orders
        WHERE date=? AND status='filled' AND reason LIKE 't_%'
        GROUP BY code
        ''',
        (trade_date,)
    ).fetchall()
    base_cfg_map = get_base_config_map(conn)
    conn.close()
    usage_map = {str(r['code']): {'used_amount': float(r['used_amount'] or 0.0), 'used_count': int(r['used_count'] or 0)} for r in usage_rows}

    cash = float(account['cash'] or 0.0)
    starting_cash = float(account['starting_cash'] or PAPER_START_CASH)
    realized = float(account['realized_pnl'] or 0.0)

    positions = []
    market_value = 0.0
    unrealized = 0.0
    with state_lock:
        lot_size = int(success_rates.get('paper_min_lot', 100))
    for r in pos_rows:
        code = r['code']
        base_cfg = base_cfg_map.get(code, {})
        base_enabled = bool(base_cfg.get('enabled')) if base_cfg else False
        base_amount = float(base_cfg.get('base_amount', 0.0)) if base_cfg else 0.0
        base_cost_line = float(base_cfg.get('base_cost_line', 0.0)) if base_cfg else 0.0
        t_order_amount = float(base_cfg.get('t_order_amount', 0.0)) if base_cfg else 0.0
        t_daily_budget = resolve_t_daily_budget(base_amount, float(base_cfg.get('t_daily_budget', 0.0)) if base_cfg else 0.0)
        t_usage = usage_map.get(code, {'used_amount': 0.0, 'used_count': 0})
        t_max_orders, t_remaining_orders = calc_t_order_caps(t_daily_budget, t_order_amount, t_usage.get('used_count', 0))
        base_target_qty = calc_base_target_qty(base_amount, base_cost_line, lot_size)
        cur_price = float(current_state.get(code, {}).get('price', r['avg_cost']) or r['avg_cost'] or 0.0)
        total_qty = int(r['total_qty'] or 0)
        mv = cur_price * total_qty
        ur = (cur_price - float(r['avg_cost'] or 0.0)) * total_qty
        market_value += mv
        unrealized += ur
        realized_pos = float(r['realized_pnl'] or 0.0)
        effective_cost_line = 0.0
        if base_enabled and base_target_qty > 0 and base_cost_line > 0:
            effective_cost_line = max(0.0, base_cost_line - realized_pos / base_target_qty)
        positions.append({
            'code': code,
            'name': r['name'],
            'total_qty': total_qty,
            'available_qty': int(r['available_qty'] or 0),
            'today_buy_qty': int(r['today_buy_qty'] or 0),
            'today_sell_qty': int(r['today_sell_qty'] or 0),
            'avg_cost': round(float(r['avg_cost'] or 0.0), 4),
            'current_price': round(cur_price, 4),
            'market_value': round(mv, 2),
            'unrealized_pnl': round(ur, 2),
            'realized_pnl': round(realized_pos, 2),
            'base_enabled': base_enabled,
            'base_amount': round(base_amount, 2),
            'base_cost_line': round(base_cost_line, 4),
            'base_target_qty': int(base_target_qty),
            'effective_cost_line': round(effective_cost_line, 4) if effective_cost_line > 0 else 0.0,
            't_order_amount': round(t_order_amount, 2),
            't_daily_budget': round(t_daily_budget, 2),
            't_used_amount': round(float(t_usage.get('used_amount', 0.0)), 2),
            't_used_count': int(t_usage.get('used_count', 0)),
            't_max_orders': int(t_max_orders),
            't_remaining_orders': int(t_remaining_orders),
            't_remaining_amount': round(max(0.0, t_daily_budget - float(t_usage.get('used_amount', 0.0))), 2),
            'updated_at': r['updated_at']
        })

    base_items = []
    for code, cfg in base_cfg_map.items():
        u = usage_map.get(code, {'used_amount': 0.0, 'used_count': 0})
        day_budget = resolve_t_daily_budget(cfg.get('base_amount', 0.0), cfg.get('t_daily_budget', 0.0))
        t_max_orders, t_remaining_orders = calc_t_order_caps(day_budget, cfg.get('t_order_amount', 0.0), u.get('used_count', 0))
        item = dict(cfg)
        item['t_used_amount'] = round(float(u.get('used_amount', 0.0)), 2)
        item['t_used_count'] = int(u.get('used_count', 0))
        item['t_max_orders'] = int(t_max_orders)
        item['t_remaining_orders'] = int(t_remaining_orders)
        item['t_remaining_amount'] = round(max(0.0, day_budget - float(u.get('used_amount', 0.0))), 2)
        base_items.append(item)

    nav = cash + market_value
    return {
        'enabled': True,
        'starting_cash': round(starting_cash, 2),
        'cash': round(cash, 2),
        'market_value': round(market_value, 2),
        'nav': round(nav, 2),
        'realized_pnl': round(realized, 2),
        'unrealized_pnl': round(unrealized, 2),
        'total_pnl': round(realized + unrealized, 2),
        'return_pct': round(((nav - starting_cash) / starting_cash * 100.0) if starting_cash > 0 else 0.0, 4),
        'positions': positions,
        'recent_orders': [dict(r) for r in order_rows],
        'base_configs': base_items
    }

def reset_paper_account(starting_cash=None):
    cash0 = float(starting_cash or PAPER_START_CASH)
    cash0 = max(10000.0, cash0)
    today = datetime.datetime.now().strftime('%Y-%m-%d')
    conn = get_db()
    conn.execute('DELETE FROM paper_orders')
    conn.execute('DELETE FROM paper_positions')
    conn.execute(
        'INSERT OR REPLACE INTO paper_account (id, starting_cash, cash, realized_pnl, updated_at) VALUES (1, ?, ?, 0.0, CURRENT_TIMESTAMP)',
        (cash0, cash0)
    )
    conn.execute(
        "INSERT OR REPLACE INTO paper_meta (k, v) VALUES ('trading_date', ?)",
        (today,)
    )
    conn.commit()
    conn.close()
    log_debug_event('paper_account_reset', {'starting_cash': cash0, 'date': today})

def parse_signal_score(desc):
    m = re.search(r'评分:(\d+)%', desc or '')
    if not m:
        return 0.0
    return int(m.group(1)) / 100.0

def get_time_slot_label(time_str=None):
    """按 A 股时段返回 slot label。"""
    try:
        if time_str and len(time_str) >= 5:
            hh = int(time_str[0:2])
            mm = int(time_str[3:5])
        else:
            now = datetime.datetime.now()
            hh, mm = now.hour, now.minute
    except Exception:
        now = datetime.datetime.now()
        hh, mm = now.hour, now.minute

    m = hh * 60 + mm
    if 9 * 60 + 30 <= m < 10 * 60:
        return 'open'
    if 10 * 60 <= m <= 11 * 60 + 30:
        return 'morning'
    if 13 * 60 <= m < 13 * 60 + 30:
        return 'afternoon_open'
    if 13 * 60 + 30 <= m < 14 * 60 + 30:
        return 'afternoon'
    if 14 * 60 + 30 <= m <= MARKET_CLOSE_MINUTE:
        return 'close'
    return 'off_hours'

def get_effective_strategy(time_str=None):
    """
    读取当前生效策略：
    - 先拿全局参数
    - 若开启 time_slot_enabled，则叠加对应时段模板
    """
    slot = get_time_slot_label(time_str)
    with state_lock:
        effective = {k: success_rates.get(k) for k in (STRATEGY_FLOAT_KEYS + STRATEGY_INT_KEYS + STRATEGY_BOOL_KEYS)}
        effective['slot'] = slot
        if effective.get('time_slot_enabled') and slot != 'off_hours':
            templates = success_rates.get('time_slot_templates', {})
            override = templates.get(slot, {}) if isinstance(templates, dict) else {}
            if isinstance(override, dict):
                for k, v in override.items():
                    effective[k] = v
    return effective

def reset_risk_state_for_day(day_str):
    with state_lock:
        risk_state['day'] = day_str
        risk_state['consecutive_fail'] = 0
        risk_state['daily_profit_pct'] = 0.0
        risk_state['paused_until_ts'] = 0.0
        risk_state['pause_reason'] = ''
        risk_state['trigger_count'] = 0

def is_risk_paused():
    now_ts = time.time()
    with state_lock:
        paused_until = float(risk_state.get('paused_until_ts', 0.0))
        reason = risk_state.get('pause_reason', '')
        if paused_until > now_ts:
            return True, max(0.0, paused_until - now_ts), reason
    return False, 0.0, ''

def maybe_trigger_risk_pause(reason, context=None):
    context = context or {}
    strategy = get_effective_strategy()
    if not strategy.get('risk_guard_enabled', True):
        return
    pause_minutes = int(strategy.get('risk_pause_minutes', 30))
    now_ts = time.time()
    with state_lock:
        risk_state['paused_until_ts'] = max(risk_state.get('paused_until_ts', 0.0), now_ts + pause_minutes * 60)
        risk_state['pause_reason'] = reason
        risk_state['trigger_count'] = int(risk_state.get('trigger_count', 0)) + 1
        paused_until = risk_state['paused_until_ts']
    log_debug_event(
        'risk_guard_triggered',
        {
            'reason': reason,
            'paused_until_ts': paused_until,
            'pause_minutes': pause_minutes,
            'context': context,
            'strategy': strategy
        }
    )

def update_risk_state_on_resolution(sig, final_status):
    now = datetime.datetime.now()
    today = now.strftime('%Y-%m-%d')
    strategy = get_effective_strategy(sig.get('time'))
    if not strategy.get('risk_guard_enabled', True):
        return

    with state_lock:
        if risk_state.get('day') != today:
            reset_risk_state_for_day(today)

        profit_pct = float(sig.get('profit_pct') or 0.0)
        risk_state['daily_profit_pct'] = float(risk_state.get('daily_profit_pct', 0.0)) + profit_pct
        if final_status == 'fail':
            risk_state['consecutive_fail'] = int(risk_state.get('consecutive_fail', 0)) + 1
        else:
            risk_state['consecutive_fail'] = 0

        consecutive_fail = int(risk_state.get('consecutive_fail', 0))
        daily_profit = float(risk_state.get('daily_profit_pct', 0.0))

    if consecutive_fail >= int(strategy.get('risk_max_consecutive_fail', 4)):
        maybe_trigger_risk_pause(
            'max_consecutive_fail_reached',
            {'consecutive_fail': consecutive_fail, 'signal_id': sig.get('id')}
        )
    if daily_profit <= float(strategy.get('risk_daily_profit_floor', -2.0)):
        maybe_trigger_risk_pause(
            'daily_profit_floor_breached',
            {'daily_profit_pct': daily_profit, 'signal_id': sig.get('id')}
        )

def init_risk_state_from_db():
    """按今日历史结果初始化风险状态，防止重启后丢失风控上下文。"""
    today = datetime.datetime.now().strftime('%Y-%m-%d')
    reset_risk_state_for_day(today)
    try:
        conn = get_db()
        rows = conn.execute(
            '''
            SELECT id, status, profit_pct
            FROM signals
            WHERE date=? AND status IN ('success','fail')
            ORDER BY COALESCE(resolved_at, created_at) ASC
            ''',
            (today,)
        ).fetchall()
        conn.close()
    except Exception as e:
        print(f"init risk state error: {e}")
        return

    for r in rows:
        fake_sig = {'id': r['id'], 'profit_pct': float(r['profit_pct'] or 0.0)}
        update_risk_state_on_resolution(fake_sig, r['status'])

def update_health_alerts():
    now_ts = time.time()
    with state_lock:
        stale = dict(health_state.get('stale_seconds_by_code', {}))
        request_errors = int(health_state.get('request_errors', 0))
        worker_errors = int(health_state.get('worker_errors', 0))
        last_fetch_ok_ts = float(health_state.get('last_fetch_ok_ts', 0.0))

    alerts = []
    for code, sec in stale.items():
        if sec >= 120:
            alerts.append({'level': 'warn', 'code': code, 'msg': f'stale {sec:.1f}s'})
    if request_errors > 0:
        alerts.append({'level': 'warn', 'msg': f'request_errors={request_errors}'})
    if worker_errors > 0:
        alerts.append({'level': 'warn', 'msg': f'worker_errors={worker_errors}'})
    if last_fetch_ok_ts > 0 and now_ts - last_fetch_ok_ts > 180:
        alerts.append({'level': 'warn', 'msg': f'last_fetch_ok {now_ts-last_fetch_ok_ts:.1f}s ago'})

    with state_lock:
        health_state['alerts'] = alerts

def load_recent_buy_outcomes(code, window):
    """从数据库加载该股票最近 window 笔 BUY 平仓结果。"""
    outcomes = collections.deque(maxlen=max(1, int(window)))
    try:
        conn = get_db()
        rows = conn.execute(
            '''
            SELECT status
            FROM signals
            WHERE code=? AND type='BUY' AND status IN ('success','fail')
            ORDER BY COALESCE(resolved_at, created_at) DESC
            LIMIT ?
            ''',
            (code, window)
        ).fetchall()
        conn.close()
        # 反转为时间正序，便于后续 append
        for r in reversed(rows):
            outcomes.append(1 if r['status'] == 'success' else 0)
    except Exception as e:
        print(f"load buy outcomes error({code}): {e}")
    return outcomes

def get_buy_pause_state(code):
    """
    返回 (is_paused, samples, win_rate)。
    BUY 质量过差时先暂停该票 BUY，SELL 不受影响。
    """
    with state_lock:
        auto_pause = bool(success_rates.get('buy_auto_pause', True))
        window = max(1, int(success_rates.get('buy_pause_window', 20)))
        min_samples = max(1, int(success_rates.get('buy_pause_min_samples', 10)))
        min_wr = float(success_rates.get('buy_pause_min_wr', 0.35))
        dq = buy_outcomes.get(code)

    if not auto_pause:
        return False, 0, 0.0

    if dq is None or dq.maxlen != window:
        loaded = load_recent_buy_outcomes(code, window)
        with state_lock:
            buy_outcomes[code] = loaded
            dq = loaded

    samples = len(dq)
    if samples < min_samples:
        return False, samples, 0.0

    wr = sum(dq) / samples if samples > 0 else 0.0
    return wr < min_wr, samples, wr

def record_buy_outcome(code, is_success):
    with state_lock:
        window = max(1, int(success_rates.get('buy_pause_window', 20)))
        dq = buy_outcomes.get(code)
        if dq is None or dq.maxlen != window:
            dq = load_recent_buy_outcomes(code, window)
            buy_outcomes[code] = dq
        dq.append(1 if is_success else 0)

def classify_trade_result(sig_type, entry_price, current_price):
    """
    统一收益判定（按净收益）：
    - gross_return: 毛收益率（小数，如 0.01 = +1%）
    - net_return: 扣除 trade_cost_buffer 后的净收益率
    - final: success / fail
    """
    entry = float(entry_price or 0.0)
    cur = float(current_price or 0.0)
    if entry <= 0:
        return 0.0, 0.0, 'fail'

    with state_lock:
        cost_buffer = float(success_rates.get('trade_cost_buffer', 0.0012))
    if str(sig_type) == 'BUY':
        gross_return = (cur - entry) / entry
    else:
        gross_return = (entry - cur) / entry
    net_return = gross_return - cost_buffer
    final = 'success' if net_return >= 0 else 'fail'
    return gross_return, net_return, final

def get_recent_regime_quality(code, sig_type, slot, lookback_days=10):
    """
    计算最近 lookback_days 的信号质量：
    - global: 指定 code + type 的整体胜率
    - slot: 指定 code + type + slot 的胜率
    """
    lookback_days = max(1, min(int(lookback_days), 60))
    end_date = datetime.datetime.now().date()
    start_date = end_date - datetime.timedelta(days=lookback_days - 1)
    key = (str(code), str(sig_type), str(slot), int(lookback_days), start_date.strftime('%Y-%m-%d'), end_date.strftime('%Y-%m-%d'))
    now_ts = time.time()
    with state_lock:
        cached = quality_cache.get(key)
    if cached and now_ts - float(cached.get('ts', 0.0)) <= 60:
        return dict(cached.get('value', {}))

    conn = get_db()
    rows = conn.execute(
        '''
        SELECT time, status, profit_pct
        FROM signals
        WHERE code=? AND type=? AND date>=? AND date<=? AND status IN ('success','fail')
        ORDER BY date DESC, time DESC
        ''',
        (code, sig_type, start_date.strftime('%Y-%m-%d'), end_date.strftime('%Y-%m-%d'))
    ).fetchall()
    conn.close()

    sample = 0
    success = 0
    profit_sum = 0.0
    slot_sample = 0
    slot_success = 0
    slot_profit_sum = 0.0
    for r in rows:
        sample += 1
        if r['status'] == 'success':
            success += 1
        profit_sum += float(r['profit_pct'] or 0.0)

        r_slot = get_time_slot_label(r['time'])
        if r_slot == slot:
            slot_sample += 1
            if r['status'] == 'success':
                slot_success += 1
            slot_profit_sum += float(r['profit_pct'] or 0.0)

    value = {
        'sample': sample,
        'win_rate': (success / sample) if sample else 0.0,
        'avg_profit_pct': (profit_sum / sample) if sample else 0.0,
        'slot_sample': slot_sample,
        'slot_win_rate': (slot_success / slot_sample) if slot_sample else 0.0,
        'slot_avg_profit_pct': (slot_profit_sum / slot_sample) if slot_sample else 0.0
    }
    with state_lock:
        quality_cache[key] = {'ts': now_ts, 'value': dict(value)}
    return value

def evaluate_regime_gate(code, sig, effective):
    """返回 (accepted, reasons, meta)，用于“只做策略内 T”过滤。"""
    with state_lock:
        enabled = bool(success_rates.get('regime_filter_enabled', True))
        target_wr = float(success_rates.get('regime_target_wr', 0.75))
        lookback_days = int(success_rates.get('regime_lookback_days', 10))
        min_samples = int(success_rates.get('regime_min_samples', 20))
        slot_min_samples = int(success_rates.get('regime_slot_min_samples', 5))
        require_trend = bool(success_rates.get('regime_require_trend_alignment', True))
        block_open_close = bool(success_rates.get('regime_block_open_close', True))
        trend_text = str(stock_contexts.get(code, {}).get('trend', ''))
        alerts = list(health_state.get('alerts', []))

    if not enabled:
        return True, [], {'regime_enabled': False}

    sig_type = str(sig.get('type', ''))
    slot = str(effective.get('slot') or get_time_slot_label(sig.get('time')))
    quality = get_recent_regime_quality(code, sig_type, slot, lookback_days=lookback_days)
    reasons = []

    if block_open_close and slot in ('open', 'close'):
        reasons.append('regime_block_open_close')

    if quality['sample'] >= min_samples and quality['win_rate'] < target_wr:
        reasons.append('regime_low_wr')
    if quality['slot_sample'] >= slot_min_samples and quality['slot_win_rate'] < target_wr:
        reasons.append('regime_slot_low_wr')

    if require_trend:
        if sig_type == 'BUY' and '空头' in trend_text:
            reasons.append('regime_trend_not_aligned')
        elif sig_type == 'SELL' and '多头' in trend_text:
            reasons.append('regime_trend_not_aligned')

    severe_alerts = []
    for a in alerts:
        msg = str(a.get('msg', ''))
        if ('stale' in msg) or ('worker_errors' in msg) or ('last_fetch_ok' in msg):
            severe_alerts.append(a)
    if severe_alerts:
        reasons.append('regime_health_unstable')

    meta = {
        'regime_enabled': True,
        'slot': slot,
        'target_wr': round(target_wr, 4),
        'lookback_days': lookback_days,
        'min_samples': min_samples,
        'slot_min_samples': slot_min_samples,
        'trend': trend_text,
        'quality': quality,
        'health_alert_count': len(alerts),
        'severe_alert_count': len(severe_alerts)
    }
    return len(reasons) == 0, reasons, meta

def should_accept_signal(code, sig):
    """信号入库前统一风控过滤。返回 (accepted, reasons, meta)。"""
    sig_type = sig.get('type')
    factors = sig.get('factors') or []
    reasons = []
    signal_time = sig.get('time')
    effective = get_effective_strategy(signal_time)
    buy_min_score = float(effective.get('buy_min_score', 0.58))
    sell_min_score = float(effective.get('sell_min_score', 0.55))
    buy_require_confirmation = bool(effective.get('buy_require_confirmation', True))
    buy_reject_bearish_tape = bool(effective.get('buy_reject_bearish_tape', True))

    # 风控总闸：暂停时一律不再开新单
    paused, left_sec, pause_reason = is_risk_paused()
    if paused:
        reasons.append('risk_guard_paused')
        meta = {
            'signal_type': sig_type,
            'slot': effective.get('slot'),
            'risk_pause_left_sec': round(left_sec, 2),
            'risk_pause_reason': pause_reason
        }
        return False, reasons, meta

    if is_pre_close_window():
        reasons.append('pre_close_no_new_position')
        return False, reasons, {
            'signal_type': sig_type,
            'slot': effective.get('slot')
        }

    regime_ok, regime_reasons, regime_meta = evaluate_regime_gate(code, sig, effective)
    if not regime_ok:
        reasons.extend(regime_reasons)
        return False, reasons, {
            'signal_type': sig_type,
            'slot': effective.get('slot'),
            'regime_meta': regime_meta
        }

    if sig_type == 'BUY':
        bull_score = float(sig.get('bull_score', parse_signal_score(sig.get('desc', ''))))
        meta = {
            'signal_type': sig_type,
            'score': round(bull_score, 4),
            'threshold': buy_min_score,
            'slot': effective.get('slot'),
            'regime_meta': regime_meta
        }
        if bull_score < buy_min_score:
            reasons.append(f"buy_score<{buy_min_score:.2f}")

        has_bull_tape = any(('多头强盘口' in f) or ('盘口偏多' in f) for f in factors)
        has_bull_volume = any('放量拉升' in f for f in factors)
        has_bear_tape = any(('空头强盘口' in f) or ('盘口偏空' in f) for f in factors)
        has_bear_volume = any('放量杀跌' in f for f in factors)
        meta.update({
            'has_bull_tape': has_bull_tape,
            'has_bull_volume': has_bull_volume,
            'has_bear_tape': has_bear_tape,
            'has_bear_volume': has_bear_volume
        })

        if buy_reject_bearish_tape and (has_bear_tape or has_bear_volume):
            reasons.append('buy_bearish_tape_detected')
        if buy_require_confirmation and not (has_bull_tape or has_bull_volume):
            reasons.append('buy_missing_confirmation')

        paused, samples, wr = get_buy_pause_state(code)
        meta.update({'buy_paused': paused, 'pause_samples': samples, 'pause_wr': round(wr, 4)})
        if paused:
            print(f"BUY paused for {code}: recent win-rate {wr:.1%} over {samples} trades")
            reasons.append('buy_auto_paused')
        return len(reasons) == 0, reasons, meta

    if sig_type == 'SELL':
        bear_score = float(sig.get('bear_score', parse_signal_score(sig.get('desc', ''))))
        accepted = bear_score >= sell_min_score
        meta = {
            'signal_type': sig_type,
            'score': round(bear_score, 4),
            'threshold': sell_min_score,
            'slot': effective.get('slot'),
            'regime_meta': regime_meta
        }
        if not accepted:
            reasons.append(f"sell_score<{sell_min_score:.2f}")
        return accepted, reasons, meta

    return False, ['unknown_signal_type'], {'signal_type': sig_type}

def resolve_pending_after_market_close(force_today=False):
    """收盘前/收盘后强制平掉未完成信号，避免跨日悬挂污染统计。"""
    now = datetime.datetime.now()
    today = now.strftime('%Y-%m-%d')

    # 交易日收盘后，或非交易日处理历史遗留；force_today 用于 14:57 前置平仓。
    after_close = (now.weekday() < 5) and ((now.hour * 60 + now.minute) > MARKET_CLOSE_MINUTE)
    non_trading = not is_trading_time()
    if not (force_today or after_close or non_trading):
        return

    db_updates = []
    debug_events = []
    phase = 'pre_close' if force_today else ('after_close' if after_close else 'non_trading')
    with state_lock:
        for sig in pending_signals[:]:
            sig_date = sig.get('date', today)
            is_stale = sig_date < today or after_close or (force_today and sig_date == today)
            if not is_stale:
                continue

            code = sig.get('code', '')
            cp = sig.get('price', 0.0)
            data_list = market_data.get(code) or []
            if data_list:
                cp = data_list[-1].get('price', cp)

            gross_return, net_return, final = classify_trade_result(sig.get('type'), sig.get('price', 0.0), cp)
            sig['status'] = final
            sig['resolved_price'] = cp
            sig['gross_profit_pct'] = gross_return * 100
            sig['profit_pct'] = net_return * 100
            sig['resolve_msg'] = (
                f"⏰ {'收盘前强制平仓' if force_today else '收盘强制平仓'} "
                f"(净{sig['profit_pct']:+.2f}% / 毛{sig['gross_profit_pct']:+.2f}%)"
            )
            hold_sec = None
            if sig.get('entry_ts'):
                hold_sec = max(0.0, time.time() - float(sig['entry_ts']))

            success_rates[final] += 1
            if code not in success_rates['stocks']:
                success_rates['stocks'][code] = {'success': 0, 'fail': 0}
            success_rates['stocks'][code][final] += 1
            if sig['type'] == 'BUY':
                record_buy_outcome(code, final == 'success')
            update_risk_state_on_resolution(sig, final)

            pending_signals.remove(sig)
            db_updates.append((sig['id'], final, cp, sig['gross_profit_pct'], sig['profit_pct'], sig['resolve_msg'], sig_date))
            debug_events.append({
                'event': 'signal_force_closed',
                'date': sig_date,
                'phase': phase,
                'time': sig.get('time', ''),
                'signal_id': sig.get('id', ''),
                'code': code,
                'name': sig.get('name', ''),
                'signal_type': sig.get('type', ''),
                'status': final,
                'entry_price': sig.get('price', 0.0),
                'resolved_price': cp,
                'gross_profit_pct': sig['gross_profit_pct'],
                'profit_pct': sig['profit_pct'],
                'hold_sec': round(hold_sec, 2) if hold_sec is not None else None,
                'resolve_msg': sig['resolve_msg'],
                'strategy': get_strategy_snapshot()
            })

        success_rates['pending'] = len(pending_signals)

    for sig_id, final, cp, gross_profit_pct, profit_pct, msg, sig_date in db_updates:
        db_resolve_signal(sig_id, final, cp, gross_profit_pct, profit_pct, msg, signal_date=sig_date)
    for e in debug_events:
        log_debug_event(e.pop('event'), e, target_date=e.get('date'))

def fetch_stock_context_bg(code):
    context = {'trend': '数据加载中', 'industry': '未知', 'news': []}
    with state_lock:
        stock_contexts[code] = context  # setup initial
    
    # 1. 行业数据 (使用东财 f10 基本资料)
    industry_name = "未知"
    concepts = ""
    try:
        secid = f"{code[:2].upper()}{code[2:]}" # e.g., SH600079
        headers = {'User-Agent': 'Mozilla/5.0'}
        resp_east = requests.get(f"http://f10.eastmoney.com/CompanySurvey/CompanySurveyAjax?code={secid}", headers=headers, timeout=3).json()
        if resp_east and 'jbzl' in resp_east:
            industry_name = resp_east['jbzl'].get('sshy', '未知')
            
        # 补充：获取核心题材
        resp_concepts = requests.get(f"http://f10.eastmoney.com/Concept/GetConceptT题材?code={secid}", headers=headers, timeout=3)
        if resp_concepts.status_code == 200:
            concepts = resp_concepts.text # raw grab since we just regex match string anyway
            
    except Exception as e:
        print(f"fetch eastmoney error: {e}")
            
    industry_html = html.escape(industry_name)
    
    # 获取板块涨跌情况 (同花顺定制 or 新浪默认)
    try:
        if code == 'sh600079':
            target_name = "💊芬太尼板块"
            try:
                import urllib.request
                import re
                req = urllib.request.Request('http://q.10jqka.com.cn/gn/detail/code/308438/', headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'})
                ths_html = urllib.request.urlopen(req, timeout=3).read().decode('gbk').replace('\n', '')
                match = re.search(r'<p class=\"board-zdf\">.*?&nbsp;&nbsp;&nbsp;&nbsp;(.*?)%</p>', ths_html)
                if match:
                    target_pct = float(match.group(1))
                else:
                    target_pct = 0.0
            except Exception as e:
                print(f"fetch ths error: {e}")
                target_pct = 0.0
        else:
            target_pct = None
            target_name = industry_name
            hy_resp = requests.get("http://vip.stock.finance.sina.com.cn/q/view/newSinaHy.php", timeout=3)
            hy_resp.encoding = 'gbk'
            import json
            hy_data = json.loads(hy_resp.text.split('=', 1)[1].strip(' ;'))
            
            # 使用更宽泛的容错兜底来尝试匹配。如果完全未匹配上，就保持现状。
            for val in hy_data.values():
                parts = val.split(',')
                if len(parts) > 5:
                    sina_ind = parts[1]
                    if sina_ind == industry_name:
                        target_pct = float(parts[5])
                        target_name = sina_ind
                        break
                    elif ("药" in industry_name and "药" in sina_ind) or ("医" in industry_name and "医" in sina_ind) or ("车" in industry_name and "车" in sina_ind):
                        target_pct = float(parts[5])
                        target_name = sina_ind
                        
        if target_pct is not None:
            icon = "🔥强势" if target_pct > 0.5 else ("🥶倒春寒" if target_pct < -0.5 else "震荡")
            color = "text-rose-400" if target_pct > 0 else "text-emerald-400"
            safe_target_name = html.escape(target_name)
            industry_html = f"<span class='text-slate-200'>{safe_target_name}</span> <span class='{color} font-bold tracking-wide pl-1'>({target_pct:+.2f}% {icon})</span>"
            
        # 追加关键概念标
        if concepts:
            if code == 'sh600079' and '芬太尼' not in concepts:
                concepts += ',芬太尼'
            hot_keywords = ['芬太尼']
            matched_concepts = [k for k in hot_keywords if k in concepts]
            if matched_concepts:
                concept_tags = "".join([f"<span class='bg-purple-600/30 text-purple-300 border border-purple-500/50 text-[10px] px-2 py-0.5 rounded-full ml-1 font-bold'>⭐{k}⭐</span>" for k in matched_concepts])
                industry_html += concept_tags
    except Exception as e:
        print(f"fetch concept error: {e}")
        
    context['industry'] = industry_html
        
    # 2. 日线数据算趋势 (30天)
    try:
        resp_k = requests.get(f"https://quotes.sina.cn/cn/api/json_v2.php/CN_MarketData.getKLineData?symbol={code}&scale=240&ma=no&datalen=30", timeout=3).json()
        if len(resp_k) >= 10:
            prices = [float(x['close']) for x in resp_k]
            ma5 = sum(prices[-5:]) / 5
            ma10 = sum(prices[-10:]) / 10
            cur = prices[-1]
            if cur > ma5 and ma5 > ma10:
                context['trend'] = '📈 日线多头跑道 (支持回调买入)'
            elif cur < ma5 and ma5 < ma10:
                context['trend'] = '📉 日线单边空头 (严禁死扛止损)'
            else:
                context['trend'] = '⚖️ 宽幅震荡期 (拉高必卖,大跌可接)'
    except Exception as e:
        print(f"fetch trend error: {e}")
            
    # 3. 最新公告/新闻 NLP 结构化分析
    news_list = []
    try:
        resp_news = requests.get(f"https://np-anotice-stock.eastmoney.com/api/security/ann?sr=-1&page_size=8&page_index=1&ann_type=A&client_source=web&stock_list={code[2:]}", timeout=3).json()
        if resp_news.get('data') and 'list' in resp_news['data']:
            for item in resp_news['data']['list']:
                title = item['title']
                art_code = item['art_code']
                time_str = item.get('notice_date', '')[:10]
                
                pos_words = ['增持', '回购', '中标', '合同', '盈利', '增长', '突破', '获批', '批准', '通过', '同意', '定增', '投资', '合作', '预增']
                neg_words = ['减持', '亏损', '立案', '调查', '风险', '处罚', '下降', '退市', '违规', '警告', '停产', '诉讼', '延期']
                pos_count = sum(1 for w in pos_words if w in title)
                neg_count = sum(1 for w in neg_words if w in title)
                
                if pos_count > neg_count:
                    badge = "<span class='text-rose-400 border border-rose-500/40 px-1 rounded-sm text-[10px] ml-1 bg-rose-500/10 font-bold tracking-wider'>利多</span>"
                    sentiment = "positive"
                elif neg_count > pos_count:
                    badge = "<span class='text-emerald-400 border border-emerald-500/40 px-1 rounded-sm text-[10px] ml-1 bg-emerald-500/10 font-bold tracking-wider'>利空</span>"
                    sentiment = "negative"
                else:
                    badge = "<span class='text-slate-400 border border-slate-500/40 px-1 rounded-sm text-[10px] ml-1 bg-slate-500/10'>中性</span>"
                    sentiment = "neutral"
                    
                news_url = f"https://data.eastmoney.com/notices/detail/{code[2:]}/{art_code}.html"
                news_list.append({'title': title, 'badge': badge, 'sentiment': sentiment, 'url': news_url, 'time': time_str})
    except Exception as e:
        print(f"fetch news error: {e}")
        
    context['news'] = news_list
    with state_lock:
        stock_contexts[code] = context

def fetch_global_market_status():
    """获取全球核心市场指数，用于大环境研判"""
    global global_market
    indices = []
    try:
        # 定义需要监控的全球核心指数
        # A50期指 (对于A股早盘预判极其重要)
        # 上证, 恒生, 纳指, 标普, 日经
        targets = [
            {'name': '上证指数', 'symbol': 'sh000001'},
            {'name': '恒生指数', 'symbol': 'hkHSI'},
            {'name': '纳斯达克', 'symbol': 'gb_ixic'},
            {'name': '标普500', 'symbol': 'gb_inx'},
            {'name': '富时A50', 'symbol': 'hf_CHA50CFD'},
            {'name': '日经225', 'symbol': 'int_nikkei'}
        ]
        
        codes = ",".join([t['symbol'] for t in targets])
        url = f"http://hq.sinajs.cn/list={codes}"
        resp = requests.get(url, headers=HEADERS, timeout=5)
        lines = resp.text.strip().split('\n')
        
        for i, line in enumerate(lines):
            if '="' in line:
                content = line.split('="')[1].split('";')[0]
                parts = content.split(',')
                if len(parts) > 3:
                    name = targets[i]['name']
                    # 不同指数解析位置不同
                    if 'gb_' in targets[i]['symbol']: # 美股
                        price = float(parts[1])
                        pct = float(parts[2])
                    elif 'hk' in targets[i]['symbol']: # 港股
                        price = float(parts[6])
                        pct = float(parts[8])
                    elif 'hf_' in targets[i]['symbol']: # A50
                        price = float(parts[0])
                        # A50计算涨跌幅需依赖昨日数据，简单拟合
                        pct = 0.0 # 默认
                    else: # A股
                        price = float(parts[3])
                        yest = float(parts[2])
                        pct = (price - yest) / yest * 100 if yest > 0 else 0
                    
                    indices.append({
                        'name': name,
                        'price': f"{price:,.2f}",
                        'pct': f"{pct:+.2f}%",
                        'is_up': pct > 0
                    })
        
        with state_lock:
            global_market['indices'] = indices
            global_market['update_time'] = datetime.datetime.now().strftime('%H:%M:%S')
    except Exception as e:
        print(f"Global market fetch error: {e}")

class DayTradeAnalyzer:
    """
    多因子评分量化引擎 v2.0
    ─────────────────────────────────────────
    信号不再由单一条件触发，而是综合5大因子打分：
    ┌─────────────────┬────────┐
    │ 因子             │ 权重   │
    ├─────────────────┼────────┤
    │ R-Breaker 关键位 │  30%   │
    │ VWAP 偏离度      │  25%   │
    │ OBI 盘口失衡     │  15%   │
    │ 成交量异动       │  15%   │
    │ 日线趋势共振     │  15%   │
    └─────────────────┴────────┘
    综合评分 ≥ 45% 且领先对手方 ≥ 8% → 触发信号
    评分 ≥ 65% → 机构级信号 (Level 2)
    """
    def __init__(self, code, window_size=60):
        self.code = code
        self.prices = collections.deque(maxlen=window_size)
        self.tick_volumes = collections.deque(maxlen=window_size)  # 每tick成交量增量
        self.prev_cum_vol = 0  # 上一tick的累计成交量，用于计算增量
        
        # R-Breaker 反转模式前置条件追踪
        self.touched_observe_sell = False  # 日内是否曾触及观察卖出位
        self.touched_observe_buy = False   # 日内是否曾触及观察买入位
        
        # 信号防重复系统（同一个价格区间不重复发信号）
        self.last_signal_type = None
        self.last_signal_price = 0
        self.last_signal_time = 0
        
        # R-Breaker parameters
        self.r_breaker = None
        self._init_r_breaker()
        
    def _init_r_breaker(self):
        try:
            url = f"https://quotes.sina.cn/cn/api/json_v2.php/CN_MarketData.getKLineData?symbol={self.code}&scale=240&ma=no&datalen=2"
            resp = requests.get(url, timeout=3)
            data = resp.json()
            if len(data) >= 2:
                import datetime
                today = datetime.datetime.now().strftime("%Y-%m-%d")
                
                yest_data = data[-2] if today in data[-1]['day'] else data[-1]
                
                H = float(yest_data['high'])
                L = float(yest_data['low'])
                C = float(yest_data['close'])
                
                pivot = (H + L + C) / 3
                self.r_breaker = {
                    'break_buy': H + 2 * (pivot - L),      # 突破买入位
                    'observe_sell': pivot + H - L,          # 观察卖出位
                    'revert_sell': 2 * pivot - L,           # 反转卖出位
                    'revert_buy': 2 * pivot - H,            # 反转买入位
                    'observe_buy': pivot - (H - L),         # 观察买入位
                    'break_sell': L - 2 * (H - pivot)       # 突破卖出位
                }
        except Exception as e:
            print(f"R-Breaker init failed for {self.code}: {e}")

    def get_signal(self, parts, vwap):
        current_price = float(parts[3])
        self.prices.append(current_price)
        
        # ---- 数据采集 ----
        
        # 成交量增量追踪（新浪数据 parts[8] 是当日累计成交量）
        tick_vol = 0
        try:
            cum_vol = int(parts[8])
            tick_vol = cum_vol - self.prev_cum_vol if self.prev_cum_vol > 0 else 0
            self.prev_cum_vol = cum_vol
            if tick_vol > 0:
                self.tick_volumes.append(tick_vol)
        except:
            pass
        
        # 今日最高/最低价（用于R-Breaker观察位判断）
        try:
            today_high = float(parts[4])
            today_low = float(parts[5])
        except:
            today_high = current_price
            today_low = current_price
        
        # OBI 盘口失衡
        try:
            buy_vols = sum(int(parts[i]) for i in (10, 12, 14, 16, 18) if i < len(parts) and parts[i])
            sell_vols = sum(int(parts[i]) for i in (20, 22, 24, 26, 28) if i < len(parts) and parts[i])
            total_vol = buy_vols + sell_vols
            obi = (buy_vols - sell_vols) / total_vol if total_vol > 0 else 0
        except:
            obi = 0
            
        if len(self.prices) < 10:
            return None
            
        # ===== 多因子评分引擎 =====
        bull_score = 0.0   # 多头证据累积
        bear_score = 0.0   # 空头证据累积
        factors = []       # 触发因子记录（用于信号描述）
        
        # ── 因子1: R-Breaker 关键位 (权重 30%) ──
        if self.r_breaker:
            rb = self.r_breaker
            
            # 利用今日真实最高/最低价追踪"是否曾触及观察位"（反转模式前置条件）
            if today_high >= rb['observe_sell']:
                self.touched_observe_sell = True
            if today_low <= rb['observe_buy']:
                self.touched_observe_buy = True
            
            # 突破模式（趋势追踪，满分0.30）
            if current_price >= rb['break_buy']:
                bull_score += 0.30
                factors.append(f"突破上轨¥{rb['break_buy']:.2f}")
            elif current_price <= rb['break_sell']:
                bear_score += 0.30
                factors.append(f"跌破下轨¥{rb['break_sell']:.2f}")
            # 反转模式（必须先触及观察位再回落/反弹，满分0.30）
            elif self.touched_observe_sell and current_price <= rb['revert_sell']:
                bear_score += 0.30
                factors.append(f"冲高回落至¥{rb['revert_sell']:.2f}")
                self.touched_observe_sell = False  # 消耗掉这个条件
            elif self.touched_observe_buy and current_price >= rb['revert_buy']:
                bull_score += 0.30
                factors.append(f"探底回升至¥{rb['revert_buy']:.2f}")
                self.touched_observe_buy = False
            # 接近关键位（部分得分，0.10）
            elif current_price <= rb['revert_buy'] * 1.005:
                bull_score += 0.10
                factors.append("接近支撑区")
            elif current_price >= rb['revert_sell'] * 0.995:
                bear_score += 0.10
                factors.append("接近压力区")
            else:
                # 中间区域：按位置给少量倾向分
                rb_range = rb['revert_sell'] - rb['revert_buy']
                if rb_range > 0:
                    position = (current_price - rb['revert_buy']) / rb_range
                    if position < 0.35:
                        bull_score += 0.06
                        factors.append("R-Breaker偏下区")
                    elif position > 0.65:
                        bear_score += 0.06
                        factors.append("R-Breaker偏上区")
        
        # ── 因子2: VWAP 偏离度 (权重 25%) ──
        if vwap > 0:
            vwap_dev = (current_price - vwap) / vwap
            abs_dev = abs(vwap_dev)
            if vwap_dev < -0.010: # 加深负偏离阈值
                bull_score += 0.25
                factors.append(f"极致超跌({vwap_dev*100:+.1f}%)")
            elif vwap_dev < -0.005:
                # 均线偏移：只有当开始收窄（V型反转）时才大幅加分
                if len(self.prices) > 2 and current_price > list(self.prices)[-2]:
                    bull_score += 0.15
                    factors.append("超跌企稳")
                else:
                    bull_score += 0.05
                    factors.append("处于VWAP下方")
            elif vwap_dev > 0.010:
                bear_score += 0.25
                factors.append(f"极致超买({vwap_dev*100:+.1f}%)")
            elif vwap_dev > 0.005:
                if len(self.prices) > 2 and current_price < list(self.prices)[-2]:
                    bear_score += 0.15
                    factors.append("冲高回落")
                else:
                    bear_score += 0.05
                    factors.append("处于VWAP上方")
        
        # ── 因子3: OBI 盘口失衡 (权重 15%) ──
        if obi > 0.35: # 提高OBI置信度
            s = 0.15
            bull_score += s
            bear_score -= 0.10 # 强力盘口直接压制反向信号
            factors.append(f"多头强盘口OBI{obi:+.0%}")
        elif obi < -0.35:
            s = 0.15
            bear_score += s
            bull_score -= 0.10
            factors.append(f"空头强盘口OBI{obi:+.0%}")
        
        # ── 因子4: 成交量异动 (权重 15%) ──
        if len(self.tick_volumes) >= 5 and tick_vol > 0:
            avg_tick_vol = sum(self.tick_volumes) / len(self.tick_volumes)
            if avg_tick_vol > 0:
                vol_ratio = tick_vol / avg_tick_vol
                if vol_ratio > 1.8:
                    # 放量方向由短期价格动量决定
                    prices_list = list(self.prices)
                    if len(prices_list) >= 3:
                        short_move = current_price - prices_list[-3]
                        if short_move > 0:
                            bull_score += 0.15
                            factors.append(f"放量拉升{vol_ratio:.1f}x")
                        elif short_move < 0:
                            bear_score += 0.15
                            factors.append(f"放量杀跌{vol_ratio:.1f}x")
        
        # ── 因子5: 日线趋势共振 (权重 15%) ──
        # (深度优化：加大逆势惩罚力度，严防空头行情接飞刀)
        trend = stock_contexts.get(self.code, {}).get('trend', '')
        if '多头' in trend:
            bull_score += 0.15
            bear_score -= 0.15  # 逆势惩罚加重
            factors.append("日线多头共振")
        elif '空头' in trend:
            bear_score += 0.15
            bull_score -= 0.20  # 空头行情严禁摸底
            factors.append("日线空头共振")
        
        # ===== 信号决策 =====
        THRESHOLD = 0.55   # 再次提高最低触发分数
        EDGE_MIN = 0.15    # 多空必须拉开的最小差距
        
        signal_type = None
        desc = ""
        level = 0
        
        if bull_score >= THRESHOLD and bull_score > bear_score + EDGE_MIN:
            signal_type = "BUY"
            level = 2 if bull_score >= 0.65 else 1
            desc = f"{'💰 机构级买点' if level == 2 else '🟢 量化预警'} [评分:{bull_score:.0%}] {'|'.join(factors)}"
        elif bear_score >= THRESHOLD and bear_score > bull_score + EDGE_MIN:
            signal_type = "SELL"
            level = 2 if bear_score >= 0.65 else 1
            desc = f"{'🔥 机构级卖点' if level == 2 else '🔴 量化预警'} [评分:{bear_score:.0%}] {'|'.join(factors)}"
        
        if signal_type:
            # === 防重复与网格过滤系统 ===
            now = time.time()
            if self.last_signal_type == signal_type:
                time_passed = now - self.last_signal_time
                if signal_type == "BUY":
                    price_diff = (current_price - self.last_signal_price) / self.last_signal_price if self.last_signal_price > 0 else 0
                    # 同为买点时：只在价格下跌超过1%(网格加仓) 或 距离上次超30分钟 时才再次触发
                    if time_passed < 1800 and price_diff > -0.01:
                        return None
                elif signal_type == "SELL":
                    price_diff = (current_price - self.last_signal_price) / self.last_signal_price if self.last_signal_price > 0 else 0
                    # 同为卖点时：只在价格上涨超过1%(网格分布) 或 距离上次超30分钟 时才再次触发
                    if time_passed < 1800 and price_diff < 0.01:
                        return None
            else:
                # ====== 新增: 异向冲突过滤 (反向锁死) ======
                # 如果当前要发出的信号方向和上一次相反(比如上次是买,这次要报卖)
                time_passed = now - self.last_signal_time
                if self.last_signal_price > 0:
                    price_diff = abs(current_price - self.last_signal_price) / self.last_signal_price
                    # 距离上次反向操作不到半小时, 且价格变动甚至没拉开1%的差距：绝对是指标在震荡期反复横跳
                    if time_passed < 1800 and price_diff < 0.01:
                        return None
            
            # 更新最后一次信号状态
            self.last_signal_type = signal_type
            self.last_signal_price = current_price
            self.last_signal_time = now

            return {
                'id': str(uuid.uuid4())[:8],
                'type': signal_type,
                'level': level,
                'price': current_price,
                'desc': desc,
                'bull_score': bull_score,
                'bear_score': bear_score,
                'factors': factors,
                'status': 'pending', 
            }
        return None

def resolve_stock_code(query):
    url = f"http://suggest3.sinajs.cn/suggest/type=&key={query}"
    try:
        resp = requests.get(url, timeout=3)
        text = resp.text
        if '=";' in text:
            return None
            
        content = text.split('="')[1].split('";')[0]
        if not content: return None
            
        items = content.split(';')
        for item in items:
            parts = item.split(',')
            # return first sh/sz A-share match
            if len(parts) > 4 and (parts[3].startswith('sh') or parts[3].startswith('sz')):
                return parts[3]
        return None
    except Exception:
        return None

def apply_add_stock(query):
    with state_lock:
        if len(active_stocks) >= MAX_STOCKS:
            return False, f"⚠️ 最多只能监控 {MAX_STOCKS} 只股票"

    resolved_code = resolve_stock_code(query)
    if not resolved_code:
        return False, f"❌ 未找到匹配的A股: {query}"

    with state_lock:
        if resolved_code in active_stocks:
            return False, "⚠️ 该股票已在监控中"

    # 获取新浪财经并验证
    url = f'http://hq.sinajs.cn/list={resolved_code}'
    try:
        resp = requests.get(url, headers=HEADERS, timeout=3)
        content = resp.text.split('="')[1].split('";')[0]
        if not content:
            return False, "❌ 无效的股票数据，可能不在交易范围内"

        name = content.split(',')[0]
        analyzer = DayTradeAnalyzer(resolved_code)

        # 此处抓取历史分时数据 (获取最近的 240 个 1分钟K线，相当于1天)
        preloaded_points = []
        try:
            history_url = f"https://quotes.sina.cn/cn/api/json_v2.php/CN_MarketData.getKLineData?symbol={resolved_code}&scale=1&ma=no&datalen=240"
            hist_resp = requests.get(history_url, timeout=3)
            hist_data = hist_resp.json()

            # 过滤只保留今天的数据
            today_str = datetime.datetime.now().strftime("%Y-%m-%d")
            hist_vol = 0
            hist_amt = 0

            for item in hist_data:
                if today_str in item.get('day', ''):
                    dt_time = item['day'].split(' ')[1]  # "10:30:00"
                    price = float(item['close'])
                    vol = float(item['volume'])
                    amt = float(item['amount'])

                    hist_vol += vol
                    hist_amt += amt
                    curr_vwap = hist_amt / hist_vol if hist_vol > 0 else price

                    preloaded_points.append({'time': dt_time, 'price': price, 'vwap': curr_vwap})
                    # 顺便填充分析器价格队列，避免初期信号缺失
                    analyzer.prices.append(price)
        except Exception as e:
            print(f"Warning: Failed to fetch history data for {resolved_code}: {e}")

        # 恢复状态机记忆，防止重启/重新添加后跳过冷却导致重复发信号
        with state_lock:
            history_snapshot = [dict(sig) for sig in signals_history if sig.get('code') == resolved_code]
        for sig in history_snapshot:
            try:
                sig_date = sig.get('date') or datetime.datetime.now().strftime('%Y-%m-%d')
                dt = datetime.datetime.strptime(
                    f"{sig_date} {sig['time']}",
                    "%Y-%m-%d %H:%M:%S"
                )
                ts = dt.timestamp()
                if ts > analyzer.last_signal_time:
                    analyzer.last_signal_time = ts
                    analyzer.last_signal_type = sig['type']
                    analyzer.last_signal_price = sig['price']
            except Exception:
                pass

        with state_lock:
            # 二次校验，防止并发添加时超过上限或重复
            if len(active_stocks) >= MAX_STOCKS:
                return False, f"⚠️ 最多只能监控 {MAX_STOCKS} 只股票"
            if resolved_code in active_stocks:
                return False, "⚠️ 该股票已在监控中"

            active_stocks[resolved_code] = name
            market_data[resolved_code] = preloaded_points
            analyzers[resolved_code] = analyzer
            # 保留恢复出来的真实冷却时间，不再重置为 0
            last_signal_time[resolved_code] = analyzer.last_signal_time
            buy_outcomes[resolved_code] = load_recent_buy_outcomes(
                resolved_code,
                max(1, int(success_rates.get('buy_pause_window', 20)))
            )

        log_debug_event(
            'stock_added',
            {
                'code': resolved_code,
                'name': name,
                'preload_points': len(preloaded_points),
                'strategy': get_strategy_snapshot()
            }
        )

        # 异步获取基本面上下文
        threading.Thread(target=fetch_stock_context_bg, args=(resolved_code,), daemon=True).start()
        return True, name
    except Exception as e:
        return False, f"网络请求发生错误: {e}"

def apply_remove_stock(code):
    removed_name = None
    with state_lock:
        if code in active_stocks:
            removed_name = active_stocks.get(code, '')
            del active_stocks[code]
            market_data.pop(code, None)
            analyzers.pop(code, None)
            last_signal_time.pop(code, None)
            stock_contexts.pop(code, None)
            stock_extras.pop(code, None)
            buy_outcomes.pop(code, None)
    if removed_name:
        log_debug_event('stock_removed', {'code': code, 'name': removed_name})

# 默认初始化监控：人福医药 + 航材股份
DEFAULT_WATCHLIST = ['sh600079', 'sh688563']
for default_code in DEFAULT_WATCHLIST:
    ok, msg = apply_add_stock(default_code)
    if not ok:
        print(f"Default watchlist add failed ({default_code}): {msg}")

def fetch_worker():
    global signals_history, success_rates, pending_signals
    global last_context_refresh

    while True:
        with state_lock:
            health_state['last_loop_ts'] = time.time()
        paper_rollover_if_new_day()
        # 每 30 分钟刷新一次全球市场与个股背景信息
        now_ts = time.time()
        if now_ts - last_context_refresh > 1800:
            with state_lock:
                refresh_codes = list(active_stocks.keys())
            fetch_global_market_status()
            for code in refresh_codes:
                threading.Thread(target=fetch_stock_context_bg, args=(code,), daemon=True).start()
            last_context_refresh = now_ts

        # 非交易时段自动休眠（节省网络资源）
        if not is_trading_time():
            resolve_pending_after_market_close()
            maybe_auto_generate_daily_report()
            time.sleep(30)
            continue

        if is_pre_close_window():
            resolve_pending_after_market_close(force_today=True)
            
        try:
            with state_lock:
                codes = list(active_stocks.keys())
            if not codes:
                time.sleep(3)
                continue
                
            codes_str = ",".join(codes)
            url = f"http://hq.sinajs.cn/list={codes_str}"
            fetch_start = time.time()
            response = requests.get(url, headers=HEADERS, timeout=5)
            fetch_latency_ms = (time.time() - fetch_start) * 1000.0
            with state_lock:
                health_state['last_fetch_latency_ms'] = round(fetch_latency_ms, 2)

            if response.status_code == 200:
                with state_lock:
                    health_state['last_fetch_ok_ts'] = time.time()
                lines = response.text.strip().split('\n')
                now_ts = time.time()
                current_prices = {}
                
                for line in lines:
                    if not line or '=";' in line: continue
                    parts_eq = line.split('=')
                    if len(parts_eq) < 2: continue
                    
                    code = parts_eq[0].split('_')[-1]
                    with state_lock:
                        analyzer = analyzers.get(code)
                    if not analyzer:
                        continue
                    
                    content = parts_eq[1].replace('"', '').replace(';', '').strip()
                    parts = content.split(',')
                    if len(parts) > 30:
                        volume = int(parts[8])
                        amount = float(parts[9])
                        daily_vwap = amount / volume if volume > 0 else 0
                        current_price = float(parts[3])
                        dt_time = parts[31]
                        
                        if current_price <= 0: continue
                        current_prices[code] = current_price
                        
                        # 存储盘口数据（前端交易窗口用）——零额外开销，数据已在parts里
                        extras_payload = None
                        try:
                            yc = float(parts[2])
                            op = float(parts[1])
                            hi = float(parts[4])
                            lo = float(parts[5])
                            # 五档盘口
                            bids = [{'p': float(parts[i+1]), 'v': int(parts[i])} for i in (10,12,14,16,18)]
                            asks = [{'p': float(parts[i+1]), 'v': int(parts[i])} for i in (20,22,24,26,28)]
                            if yc > 0:
                                extras_payload = {
                                    'yest_close': yc, 'open_price': op,
                                    'high': hi, 'low': lo,
                                    'volume': volume, 'amount': amount,
                                    'bids': bids, 'asks': asks
                                }
                        except:
                            with state_lock:
                                health_state['parse_errors'] = int(health_state.get('parse_errors', 0)) + 1
                        if extras_payload:
                            with state_lock:
                                if code in active_stocks:
                                    stock_extras[code] = extras_payload
                        
                        with state_lock:
                            data_list = market_data.get(code)
                            if data_list is None:
                                continue

                            # 防重复录入
                            if len(data_list) > 0 and data_list[-1]['time'] == dt_time:
                                continue

                            point = {'time': dt_time, 'price': current_price, 'vwap': daily_vwap}
                            data_list.append(point)
                            if len(data_list) > 4800:
                                data_list.pop(0)
                            health_state['last_tick_by_code'][code] = time.time()

                        # 获取预警信号 (冷却120s)
                        new_sig = analyzer.get_signal(parts, daily_vwap)
                        if new_sig:
                            should_persist = False
                            with state_lock:
                                stock_name = active_stocks.get(code)
                                cooldown_elapsed = now_ts - last_signal_time.get(code, 0)

                            if not stock_name:
                                continue

                            base_payload = {
                                'date': datetime.datetime.now().strftime('%Y-%m-%d'),
                                'time': dt_time,
                                'code': code,
                                'name': stock_name,
                                'signal_type': new_sig.get('type'),
                                'price': round(float(new_sig.get('price', 0.0)), 4),
                                'bull_score': round(float(new_sig.get('bull_score', 0.0)), 4),
                                'bear_score': round(float(new_sig.get('bear_score', 0.0)), 4),
                                'factors': list(new_sig.get('factors') or []),
                                'desc': new_sig.get('desc', '')
                            }
                            new_sig['time'] = dt_time

                            if cooldown_elapsed <= 120:
                                log_debug_event(
                                    'signal_skipped_cooldown',
                                    {
                                        **base_payload,
                                        'cooldown_left_sec': round(120 - cooldown_elapsed, 2),
                                        'strategy': get_strategy_snapshot()
                                    },
                                    target_date=base_payload['date']
                                )
                                continue

                            accepted, reject_reasons, filter_meta = should_accept_signal(code, new_sig)
                            if not accepted:
                                log_debug_event(
                                    'signal_rejected',
                                    {
                                        **base_payload,
                                        'reasons': reject_reasons,
                                        'filter_meta': filter_meta,
                                        'strategy': get_strategy_snapshot()
                                    },
                                    target_date=base_payload['date']
                                )
                                continue

                            signal_seq_no = get_next_signal_seq(code, base_payload['date'])

                            with state_lock:
                                # 入库前再做一次并发态校验
                                if code not in active_stocks:
                                    continue
                                if now_ts - last_signal_time.get(code, 0) <= 120:
                                    continue

                                new_sig['time'] = dt_time
                                new_sig['date'] = base_payload['date']
                                new_sig['code'] = code
                                new_sig['name'] = active_stocks[code]
                                new_sig['seq_no'] = signal_seq_no
                                new_sig['entry_ts'] = now_ts

                                signals_history.insert(0, new_sig)
                                if len(signals_history) > 100:
                                    signals_history.pop()
                                pending_signals.append(new_sig)
                                success_rates['total'] += 1
                                last_signal_time[code] = now_ts
                                should_persist = True
                            if should_persist:
                                db_save_signal(new_sig)  # 持久化
                                log_debug_event(
                                    'signal_accepted',
                                    {
                                        **base_payload,
                                        'signal_id': new_sig.get('id'),
                                        'seq_no': new_sig.get('seq_no'),
                                        'filter_meta': filter_meta,
                                        'strategy': get_strategy_snapshot()
                                    },
                                    target_date=base_payload['date']
                                )
                                paper_result = maybe_execute_paper_trade(new_sig, current_prices.get(code, new_sig.get('price', 0.0)))
                                with state_lock:
                                    new_sig['paper'] = paper_result
                
                # === 移动止损系统 (Trailing Stop) ===
                db_updates = []
                debug_events = []
                with state_lock:
                    win_threshold = success_rates.get('win_threshold', 0.015)
                    loss_threshold = success_rates.get('loss_threshold', 0.008)

                    for sig in pending_signals[:]:
                        code = sig['code']
                        if code not in current_prices:
                            continue
                        cp = current_prices[code]

                        # 初始化动态止损价和止盈价
                        if 'stop_price' not in sig:
                            if sig['type'] == 'BUY':
                                sig['stop_price'] = sig['price'] * (1 - loss_threshold)
                                sig['win_price'] = sig['price'] * (1 + win_threshold)
                            else:
                                sig['stop_price'] = sig['price'] * (1 + loss_threshold)
                                sig['win_price'] = sig['price'] * (1 - win_threshold)

                        if sig['type'] == 'BUY':
                            profit_pct = (cp - sig['price']) / sig['price']
                            hold_sec = None
                            if sig.get('entry_ts'):
                                hold_sec = max(0.0, time.time() - float(sig['entry_ts']))
                            # 优化移动止损：浮盈0.5%保本，浮盈0.8%锁定0.4%
                            if profit_pct >= 0.008:
                                sig['stop_price'] = max(sig['stop_price'], sig['price'] * 1.004)
                            elif profit_pct >= 0.005:
                                sig['stop_price'] = max(sig['stop_price'], sig['price'] * 1.001)

                            if cp >= sig['price'] * (1 + win_threshold):
                                gross_return, net_return, final = classify_trade_result(sig.get('type'), sig.get('price', 0.0), cp)
                                sig['status'] = final
                                sig['resolved_price'] = cp
                                sig['gross_profit_pct'] = gross_return * 100
                                sig['profit_pct'] = net_return * 100
                                sig['resolve_msg'] = f"🎯 止盈平仓 (净{sig['profit_pct']:+.2f}% / 毛{sig['gross_profit_pct']:+.2f}%)"
                                success_rates[final] += 1
                                if code not in success_rates['stocks']:
                                    success_rates['stocks'][code] = {'success': 0, 'fail': 0}
                                success_rates['stocks'][code][final] += 1
                                if sig['type'] == 'BUY':
                                    record_buy_outcome(code, final == 'success')
                                update_risk_state_on_resolution(sig, final)
                                pending_signals.remove(sig)
                                db_updates.append((sig['id'], final, cp, sig['gross_profit_pct'], sig['profit_pct'], sig['resolve_msg'], sig.get('date')))
                                debug_events.append({
                                    'event': 'signal_resolved',
                                    'date': sig.get('date'),
                                    'time': sig.get('time', ''),
                                    'signal_id': sig.get('id', ''),
                                    'code': code,
                                    'name': sig.get('name', ''),
                                    'signal_type': sig.get('type', ''),
                                    'status': final,
                                    'entry_price': sig.get('price', 0.0),
                                    'resolved_price': cp,
                                    'gross_profit_pct': sig['gross_profit_pct'],
                                    'profit_pct': sig['profit_pct'],
                                    'hold_sec': round(hold_sec, 2) if hold_sec is not None else None,
                                    'resolve_msg': sig.get('resolve_msg', ''),
                                    'strategy': get_strategy_snapshot()
                                })
                            elif cp <= sig['stop_price']:
                                gross_return, net_return, final = classify_trade_result(sig.get('type'), sig.get('price', 0.0), cp)
                                sig['status'] = final
                                sig['resolved_price'] = cp
                                sig['gross_profit_pct'] = gross_return * 100
                                sig['profit_pct'] = net_return * 100
                                sig['resolve_msg'] = f"🛡️ 止损/保本平仓 (净{sig['profit_pct']:+.2f}% / 毛{sig['gross_profit_pct']:+.2f}%)"
                                success_rates[final] += 1
                                if code not in success_rates['stocks']:
                                    success_rates['stocks'][code] = {'success': 0, 'fail': 0}
                                success_rates['stocks'][code][final] += 1
                                if sig['type'] == 'BUY':
                                    record_buy_outcome(code, final == 'success')
                                update_risk_state_on_resolution(sig, final)
                                pending_signals.remove(sig)
                                db_updates.append((sig['id'], final, cp, sig['gross_profit_pct'], sig['profit_pct'], sig['resolve_msg'], sig.get('date')))
                                debug_events.append({
                                    'event': 'signal_resolved',
                                    'date': sig.get('date'),
                                    'time': sig.get('time', ''),
                                    'signal_id': sig.get('id', ''),
                                    'code': code,
                                    'name': sig.get('name', ''),
                                    'signal_type': sig.get('type', ''),
                                    'status': final,
                                    'entry_price': sig.get('price', 0.0),
                                    'resolved_price': cp,
                                    'gross_profit_pct': sig['gross_profit_pct'],
                                    'profit_pct': sig['profit_pct'],
                                    'hold_sec': round(hold_sec, 2) if hold_sec is not None else None,
                                    'resolve_msg': sig.get('resolve_msg', ''),
                                    'strategy': get_strategy_snapshot()
                                })

                        elif sig['type'] == 'SELL':
                            profit_pct = (sig['price'] - cp) / sig['price']
                            hold_sec = None
                            if sig.get('entry_ts'):
                                hold_sec = max(0.0, time.time() - float(sig['entry_ts']))
                            # 优化移动止损：浮盈0.5%保本，浮盈0.8%锁定0.4%
                            if profit_pct >= 0.008:
                                sig['stop_price'] = min(sig['stop_price'], sig['price'] * 0.996)
                            elif profit_pct >= 0.005:
                                sig['stop_price'] = min(sig['stop_price'], sig['price'] * 0.999)

                            if cp <= sig['price'] * (1 - win_threshold):
                                gross_return, net_return, final = classify_trade_result(sig.get('type'), sig.get('price', 0.0), cp)
                                sig['status'] = final
                                sig['resolved_price'] = cp
                                sig['gross_profit_pct'] = gross_return * 100
                                sig['profit_pct'] = net_return * 100
                                sig['resolve_msg'] = f"🎯 止盈平仓 (净{sig['profit_pct']:+.2f}% / 毛{sig['gross_profit_pct']:+.2f}%)"
                                success_rates[final] += 1
                                if code not in success_rates['stocks']:
                                    success_rates['stocks'][code] = {'success': 0, 'fail': 0}
                                success_rates['stocks'][code][final] += 1
                                update_risk_state_on_resolution(sig, final)
                                pending_signals.remove(sig)
                                db_updates.append((sig['id'], final, cp, sig['gross_profit_pct'], sig['profit_pct'], sig['resolve_msg'], sig.get('date')))
                                debug_events.append({
                                    'event': 'signal_resolved',
                                    'date': sig.get('date'),
                                    'time': sig.get('time', ''),
                                    'signal_id': sig.get('id', ''),
                                    'code': code,
                                    'name': sig.get('name', ''),
                                    'signal_type': sig.get('type', ''),
                                    'status': final,
                                    'entry_price': sig.get('price', 0.0),
                                    'resolved_price': cp,
                                    'gross_profit_pct': sig['gross_profit_pct'],
                                    'profit_pct': sig['profit_pct'],
                                    'hold_sec': round(hold_sec, 2) if hold_sec is not None else None,
                                    'resolve_msg': sig.get('resolve_msg', ''),
                                    'strategy': get_strategy_snapshot()
                                })
                            elif cp >= sig['stop_price']:
                                gross_return, net_return, final = classify_trade_result(sig.get('type'), sig.get('price', 0.0), cp)
                                sig['status'] = final
                                sig['resolved_price'] = cp
                                sig['gross_profit_pct'] = gross_return * 100
                                sig['profit_pct'] = net_return * 100
                                sig['resolve_msg'] = f"🛡️ 止损/保本平仓 (净{sig['profit_pct']:+.2f}% / 毛{sig['gross_profit_pct']:+.2f}%)"
                                success_rates[final] += 1
                                if code not in success_rates['stocks']:
                                    success_rates['stocks'][code] = {'success': 0, 'fail': 0}
                                success_rates['stocks'][code][final] += 1
                                update_risk_state_on_resolution(sig, final)
                                pending_signals.remove(sig)
                                db_updates.append((sig['id'], final, cp, sig['gross_profit_pct'], sig['profit_pct'], sig['resolve_msg'], sig.get('date')))
                                debug_events.append({
                                    'event': 'signal_resolved',
                                    'date': sig.get('date'),
                                    'time': sig.get('time', ''),
                                    'signal_id': sig.get('id', ''),
                                    'code': code,
                                    'name': sig.get('name', ''),
                                    'signal_type': sig.get('type', ''),
                                    'status': final,
                                    'entry_price': sig.get('price', 0.0),
                                    'resolved_price': cp,
                                    'gross_profit_pct': sig['gross_profit_pct'],
                                    'profit_pct': sig['profit_pct'],
                                    'hold_sec': round(hold_sec, 2) if hold_sec is not None else None,
                                    'resolve_msg': sig.get('resolve_msg', ''),
                                    'strategy': get_strategy_snapshot()
                                })

                    success_rates['pending'] = len(pending_signals)

                for sig_id, final_status, resolved_price, gross_profit_pct, profit_pct, resolve_msg, sig_date in db_updates:
                    db_resolve_signal(sig_id, final_status, resolved_price, gross_profit_pct, profit_pct, resolve_msg, signal_date=sig_date)
                for e in debug_events:
                    log_debug_event(e.pop('event'), e, target_date=e.get('date'))
            else:
                with state_lock:
                    health_state['request_errors'] = int(health_state.get('request_errors', 0)) + 1
                    health_state['last_error'] = f'hq status={response.status_code}'
                log_debug_event('fetch_non_200', {'status_code': response.status_code, 'url': url})

            # 刷新数据新鲜度指标
            now_tick = time.time()
            with state_lock:
                stale_map = {}
                for c in codes:
                    last_tick_ts = health_state['last_tick_by_code'].get(c, 0.0)
                    stale_map[c] = round(now_tick - last_tick_ts, 2) if last_tick_ts > 0 else 9999.0
                health_state['stale_seconds_by_code'] = stale_map
            update_health_alerts()
                
        except Exception as e:
            print(f"[{time.strftime('%X')}] Worker error: {e}")
            with state_lock:
                health_state['worker_errors'] = int(health_state.get('worker_errors', 0)) + 1
                health_state['last_error'] = str(e)
            log_debug_event('worker_error', {'error': str(e)})
            
        time.sleep(3)

# === Routing ==================================================

from flask import make_response

@app.route('/')
def index():
    resp = make_response(render_template('index.html'))
    resp.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, post-check=0, pre-check=0, max-age=0'
    resp.headers['Pragma'] = 'no-cache'
    resp.headers['Expires'] = '-1'
    return resp

@app.route('/api/data')
def get_data():
    with state_lock:
        active_stocks_snapshot = dict(active_stocks)
        market_data_snapshot = {code: list(points) for code, points in market_data.items()}
        signals_snapshot = [dict(sig) for sig in signals_history]
        pending_snapshot = [dict(sig) for sig in pending_signals]
        stats_snapshot = copy.deepcopy(success_rates)
        contexts_snapshot = {
            code: {
                'trend': ctx.get('trend', ''),
                'industry': ctx.get('industry', ''),
                'news': [dict(n) for n in ctx.get('news', [])]
            }
            for code, ctx in stock_contexts.items()
        }
        rb_levels = {
            code: dict(analyzer.r_breaker)
            for code, analyzer in analyzers.items()
            if analyzer.r_breaker
        }
        extras_snapshot = copy.deepcopy(stock_extras)
        global_snapshot = {
            'indices': [dict(item) for item in global_market.get('indices', [])],
            'update_time': global_market.get('update_time', '')
        }

    current_state = {}
    for code, data_list in market_data_snapshot.items():
        if data_list:
            extras = extras_snapshot.get(code, {})
            current_state[code] = {
                'name': active_stocks_snapshot.get(code, ''),
                'price': data_list[-1]['price'],
                'vwap': data_list[-1]['vwap'],
                'yest_close': extras.get('yest_close', 0),
                'open_price': extras.get('open_price', 0)
            }
    pre_close_snapshot = build_pre_close_alert_snapshot(pending_snapshot, current_state)
    paper_snapshot = get_paper_snapshot(current_state, recent_limit=20)

    return jsonify({
        'active_stocks': active_stocks_snapshot,
        'market_data': market_data_snapshot,
        'current': current_state,
        'signals': signals_snapshot,
        'stats': stats_snapshot,
        'contexts': contexts_snapshot,
        'r_breaker': rb_levels,
        'extras': extras_snapshot,
        'global': global_snapshot,
        'pre_close': pre_close_snapshot,
        'paper': paper_snapshot,
        'is_trading': is_trading_time()
    })

@app.route('/api/health')
def api_health():
    now_ts = time.time()
    with state_lock:
        health_snapshot = copy.deepcopy(health_state)
        active_codes = list(active_stocks.keys())
        pending_n = len(pending_signals)
        risk_snapshot = copy.deepcopy(risk_state)

    loop_age = now_ts - float(health_snapshot.get('last_loop_ts') or 0.0) if health_snapshot.get('last_loop_ts') else None
    fetch_age = now_ts - float(health_snapshot.get('last_fetch_ok_ts') or 0.0) if health_snapshot.get('last_fetch_ok_ts') else None
    paused, left_sec, reason = is_risk_paused()

    status = 'ok'
    alerts = list(health_snapshot.get('alerts', []))
    if loop_age is not None and loop_age > 30:
        alerts.append({'level': 'warn', 'msg': f'worker loop age {loop_age:.1f}s'})
    if fetch_age is not None and is_trading_time() and fetch_age > 120:
        alerts.append({'level': 'warn', 'msg': f'fetch age {fetch_age:.1f}s'})
    if paused:
        alerts.append({'level': 'warn', 'msg': f'risk paused {left_sec:.1f}s ({reason})'})
    if alerts:
        status = 'warn'

    return jsonify({
        'status': status,
        'ts': datetime.datetime.now().isoformat(timespec='seconds'),
        'is_trading': is_trading_time(),
        'active_codes': active_codes,
        'pending_signals': pending_n,
        'worker_loop_age_sec': round(loop_age, 2) if loop_age is not None else None,
        'last_fetch_age_sec': round(fetch_age, 2) if fetch_age is not None else None,
        'health': health_snapshot,
        'risk': risk_snapshot,
        'risk_paused': paused,
        'risk_pause_left_sec': round(left_sec, 2),
        'risk_pause_reason': reason,
        'alerts': alerts
    })

@app.route('/api/paper/account')
def api_paper_account():
    with state_lock:
        current_state = {}
        for code, data_list in market_data.items():
            if data_list:
                current_state[code] = {'price': data_list[-1].get('price', 0.0)}
    try:
        limit = int(request.args.get('limit', 30))
    except Exception:
        limit = 30
    snapshot = get_paper_snapshot(current_state, recent_limit=limit)
    return jsonify({'success': True, 'paper': snapshot})

@app.route('/api/paper/reset', methods=['POST'])
def api_paper_reset():
    data = request.get_json(silent=True) or {}
    confirm = to_bool(data.get('confirm', False))
    if not confirm:
        return jsonify({'success': False, 'msg': 'missing confirm=true'})
    try:
        starting_cash = float(data.get('starting_cash', PAPER_START_CASH))
    except Exception:
        starting_cash = PAPER_START_CASH
    reset_paper_account(starting_cash=starting_cash)
    snapshot = get_paper_snapshot({}, recent_limit=20)
    return jsonify({'success': True, 'paper': snapshot})

@app.route('/api/paper/base-config', methods=['GET'])
def api_paper_base_config_list():
    return jsonify({'success': True, 'items': list_base_configs()})

@app.route('/api/paper/base-config', methods=['POST'])
def api_paper_base_config_upsert():
    data = request.get_json(silent=True) or {}
    items = data.get('items')
    if not isinstance(items, list):
        items = [data]
    results = []
    for item in items:
        ok, msg = upsert_base_config(
            item.get('code'),
            item.get('name', ''),
            item.get('base_amount', 0.0),
            item.get('base_cost_line', 0.0),
            enabled=to_bool(item.get('enabled', True)),
            t_order_amount=item.get('t_order_amount', 0.0),
            t_daily_budget=item.get('t_daily_budget', 0.0),
            t_costline_strength=item.get('t_costline_strength', 1.0)
        )
        results.append({
            'code': (item.get('code') or '').lower(),
            'success': ok,
            'msg': msg
        })

    apply_seed = to_bool(data.get('apply_seed', False))
    reseed = to_bool(data.get('reseed', False))
    applied = []
    if apply_seed:
        applied = seed_base_positions(reseed=reseed)
    snapshot = get_paper_snapshot({}, recent_limit=20)
    return jsonify({
        'success': all(r['success'] for r in results),
        'results': results,
        'applied': applied,
        'paper': snapshot
    })

@app.route('/api/paper/base-config/seed', methods=['POST'])
def api_paper_base_seed():
    data = request.get_json(silent=True) or {}
    reseed = to_bool(data.get('reseed', False))
    applied = seed_base_positions(reseed=reseed)
    snapshot = get_paper_snapshot({}, recent_limit=20)
    return jsonify({'success': True, 'applied': applied, 'paper': snapshot})

@app.route('/api/stocks', methods=['POST'])
def api_add_stock():
    payload = request.get_json(silent=True) or {}
    code = payload.get('code', '').strip().lower()
    success, msg = apply_add_stock(code)
    return jsonify({'success': success, 'msg': msg})

@app.route('/api/config', methods=['POST'])
def update_config():
    data = request.get_json(silent=True) or {}
    try:
        ok, errors, applied = apply_strategy_patch(data)
        if not ok:
            log_debug_event('config_update_failed', {'changes': data, 'errors': errors})
            return jsonify({'success': False, 'msg': 'invalid config', 'errors': errors})

        log_debug_event(
            'config_updated',
            {
                'changes': applied,
                'strategy': get_strategy_snapshot()
            }
        )

        return jsonify({'success': True, 'applied': applied})
    except Exception as e:
        log_debug_event('config_update_failed', {'changes': data, 'error': str(e)})
        return jsonify({'success': False, 'msg': str(e)})

@app.route('/api/config/snapshots', methods=['GET'])
def api_list_config_snapshots():
    try:
        limit = int(request.args.get('limit', 30))
    except Exception:
        limit = 30
    items = list_param_versions(limit=limit)
    return jsonify({'success': True, 'items': items})

@app.route('/api/config/snapshots', methods=['POST'])
def api_save_config_snapshot():
    data = request.get_json(silent=True) or {}
    note = data.get('note', '')
    version_id, snapshot = save_param_version(note=note)
    log_debug_event(
        'config_snapshot_saved',
        {'version_id': version_id, 'note': note, 'strategy': snapshot}
    )
    return jsonify({'success': True, 'id': version_id, 'note': note, 'params': snapshot})

@app.route('/api/config/rollback', methods=['POST'])
def api_config_rollback():
    data = request.get_json(silent=True) or {}
    version_id = data.get('id')
    if version_id is None:
        return jsonify({'success': False, 'msg': 'missing id'})
    try:
        version_id = int(version_id)
    except Exception:
        return jsonify({'success': False, 'msg': 'invalid id'})

    version = get_param_version(version_id)
    if not version:
        return jsonify({'success': False, 'msg': f'param version not found: {version_id}'})

    ok, errors, applied = apply_strategy_patch(version.get('params', {}))
    if not ok:
        log_debug_event(
            'config_rollback_failed',
            {'version_id': version_id, 'errors': errors, 'raw_params': version.get('params', {})}
        )
        return jsonify({'success': False, 'msg': 'rollback apply failed', 'errors': errors})

    log_debug_event(
        'config_rollback_applied',
        {
            'version_id': version_id,
            'note': version.get('note', ''),
            'changes': applied,
            'strategy': get_strategy_snapshot()
        }
    )
    return jsonify({
        'success': True,
        'version_id': version_id,
        'note': version.get('note', ''),
        'applied': applied
    })

@app.route('/api/stocks/<code>', methods=['DELETE'])
def api_remove_stock(code):
    apply_remove_stock(code.lower())
    return jsonify({'success': True})

@app.route('/api/history')
def api_history():
    """查询历史信号：?date=2026-02-27 或 ?days=7"""
    try:
        conn = get_db()
        date_q = request.args.get('date')
        days_q = int(request.args.get('days', 7))
        
        if date_q:
            signals = conn.execute('SELECT * FROM signals WHERE date=? ORDER BY created_at DESC', (date_q,)).fetchall()
            stats = conn.execute('SELECT * FROM daily_stats WHERE date=?', (date_q,)).fetchone()
        else:
            since = (datetime.datetime.now() - datetime.timedelta(days=days_q)).strftime('%Y-%m-%d')
            signals = conn.execute('SELECT * FROM signals WHERE date>=? ORDER BY date DESC, created_at DESC', (since,)).fetchall()
            stats = None
        
        # 获取每日汇总
        daily = conn.execute('SELECT * FROM daily_stats ORDER BY date DESC LIMIT ?', (days_q,)).fetchall()
        conn.close()
        
        return jsonify({
            'signals': [dict(r) for r in signals],
            'daily_stats': [dict(r) for r in daily],
            'date_stats': dict(stats) if stats else None
        })
    except Exception as e:
        return jsonify({'error': str(e)})

def read_debug_log_entries(target_date, limit=500):
    path = get_debug_log_path(target_date)
    if not os.path.exists(path):
        return []

    entries = []
    with debug_log_lock:
        try:
            with open(path, 'r', encoding='utf-8') as f:
                lines = f.readlines()
        except Exception:
            return []

    for line in lines[-limit:]:
        line = line.strip()
        if not line:
            continue
        try:
            entries.append(json.loads(line))
        except Exception:
            continue
    return entries

def summarize_debug_entries(entries):
    event_counts = collections.Counter()
    reject_reasons = collections.Counter()
    by_code = collections.defaultdict(lambda: {'accepted': 0, 'rejected': 0, 'resolved_success': 0, 'resolved_fail': 0})
    by_type = collections.defaultdict(lambda: {'accepted': 0, 'rejected': 0, 'resolved_success': 0, 'resolved_fail': 0})

    for e in entries:
        evt = e.get('event', '')
        event_counts[evt] += 1
        code = str(e.get('code', ''))
        sig_type = str(e.get('signal_type', ''))

        if evt == 'signal_rejected':
            by_code[code]['rejected'] += 1
            by_type[sig_type]['rejected'] += 1
            for r in e.get('reasons') or []:
                reject_reasons[str(r)] += 1
        elif evt == 'signal_accepted':
            by_code[code]['accepted'] += 1
            by_type[sig_type]['accepted'] += 1
        elif evt in ('signal_resolved', 'signal_force_closed'):
            status = e.get('status')
            if status == 'success':
                by_code[code]['resolved_success'] += 1
                by_type[sig_type]['resolved_success'] += 1
            elif status == 'fail':
                by_code[code]['resolved_fail'] += 1
                by_type[sig_type]['resolved_fail'] += 1

    return {
        'event_counts': dict(event_counts),
        'reject_reasons': dict(reject_reasons),
        'by_code': dict(by_code),
        'by_type': dict(by_type),
        'sample_size': len(entries)
    }

def get_daily_report_paths(target_date):
    os.makedirs(REPORT_DIR, exist_ok=True)
    return {
        'json': os.path.join(REPORT_DIR, f'{target_date}.json'),
        'md': os.path.join(REPORT_DIR, f'{target_date}.md')
    }

def get_daily_bundle_path(target_date):
    os.makedirs(BUNDLE_DIR, exist_ok=True)
    return os.path.join(BUNDLE_DIR, f'{target_date}.json')

def get_signal_rows(date_from=None, date_to=None):
    conn = get_db()
    where = []
    params = []
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
        tuple(params)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def compute_slot_performance(days=1, end_date=None):
    end_date = normalize_date_str(end_date, fallback_today=True)
    if not end_date:
        end_date = datetime.datetime.now().strftime('%Y-%m-%d')
    try:
        end_dt = datetime.datetime.strptime(end_date, '%Y-%m-%d').date()
    except Exception:
        end_dt = datetime.datetime.now().date()
    days = max(1, min(int(days), 90))
    start_dt = end_dt - datetime.timedelta(days=days - 1)

    rows = get_signal_rows(date_from=start_dt.strftime('%Y-%m-%d'), date_to=end_dt.strftime('%Y-%m-%d'))
    agg = collections.defaultdict(lambda: {'total': 0, 'success': 0, 'fail': 0, 'pending': 0, 'profit_sum': 0.0, 'profit_n': 0})
    agg_type = collections.defaultdict(lambda: collections.defaultdict(lambda: {'total': 0, 'success': 0, 'fail': 0, 'pending': 0, 'profit_sum': 0.0, 'profit_n': 0}))

    for r in rows:
        slot = get_time_slot_label(r.get('time'))
        st = agg[slot]
        st_type = agg_type[slot][r.get('type', 'UNKNOWN')]

        for target in (st, st_type):
            target['total'] += 1
            status = r.get('status')
            if status == 'success':
                target['success'] += 1
                target['profit_sum'] += float(r.get('profit_pct') or 0.0)
                target['profit_n'] += 1
            elif status == 'fail':
                target['fail'] += 1
                target['profit_sum'] += float(r.get('profit_pct') or 0.0)
                target['profit_n'] += 1
            else:
                target['pending'] += 1

    slot_items = []
    for slot, st in agg.items():
        comp = st['success'] + st['fail']
        by_type = {}
        for sig_type, st_type in agg_type[slot].items():
            c2 = st_type['success'] + st_type['fail']
            by_type[sig_type] = {
                'total': st_type['total'],
                'success': st_type['success'],
                'fail': st_type['fail'],
                'pending': st_type['pending'],
                'win_rate': round(st_type['success'] * 100.0 / c2, 2) if c2 else 0.0,
                'avg_profit_pct': round(st_type['profit_sum'] / st_type['profit_n'], 4) if st_type['profit_n'] else 0.0
            }
        slot_items.append({
            'slot': slot,
            'total': st['total'],
            'success': st['success'],
            'fail': st['fail'],
            'pending': st['pending'],
            'win_rate': round(st['success'] * 100.0 / comp, 2) if comp else 0.0,
            'avg_profit_pct': round(st['profit_sum'] / st['profit_n'], 4) if st['profit_n'] else 0.0,
            'by_type': by_type
        })
    slot_items.sort(key=lambda x: x['total'], reverse=True)

    return {
        'date_range': {
            'from': start_dt.strftime('%Y-%m-%d'),
            'to': end_dt.strftime('%Y-%m-%d'),
            'days': days
        },
        'items': slot_items
    }

def build_slot_hints(slot_perf):
    hints = []
    for item in slot_perf.get('items', []):
        slot = item['slot']
        total = int(item.get('total', 0))
        wr = float(item.get('win_rate', 0.0))
        buy = item.get('by_type', {}).get('BUY', {})
        buy_total = int(buy.get('total', 0))
        buy_wr = float(buy.get('win_rate', 0.0))
        if total >= 6 and wr < 40:
            hints.append({
                'slot': slot,
                'severity': 'warn',
                'msg': f'{slot} 胜率偏低({wr:.1f}%)，建议提高时段阈值或降低仓位'
            })
        if buy_total >= 4 and buy_wr < 35:
            hints.append({
                'slot': slot,
                'severity': 'warn',
                'msg': f'{slot} BUY 胜率偏低({buy_wr:.1f}%)，建议上调 time_slot_templates.{slot}.buy_min_score'
            })
        if total >= 6 and wr >= 65:
            hints.append({
                'slot': slot,
                'severity': 'info',
                'msg': f'{slot} 胜率较高({wr:.1f}%)，可作为优先交易时段'
            })
    return hints

def read_daily_bundle_json(target_date):
    path = get_daily_bundle_path(target_date)
    if not os.path.exists(path):
        return None
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return None

def get_latest_tuning_for_date(target_date):
    os.makedirs(TUNING_DIR, exist_ok=True)
    prefix = f"{target_date}_"
    files = [f for f in os.listdir(TUNING_DIR) if f.startswith(prefix) and f.endswith('.json')]
    if not files:
        return None
    files.sort(reverse=True)
    path = os.path.join(TUNING_DIR, files[0])
    try:
        with open(path, 'r', encoding='utf-8') as f:
            payload = json.load(f)
        return {'path': path, 'payload': payload}
    except Exception:
        return {'path': path, 'payload': None}

def generate_daily_bundle(target_date, trigger='manual'):
    report, report_paths = get_or_generate_daily_report(target_date, trigger=f'bundle_{trigger}')
    debug_entries = read_debug_log_entries(target_date, limit=50000)
    debug_summary = summarize_debug_entries(debug_entries)
    slot_perf = compute_slot_performance(days=1, end_date=target_date)
    slot_hints = build_slot_hints(slot_perf)
    latest_tuning = get_latest_tuning_for_date(target_date)
    preflight = build_preflight_assessment(ref_date=target_date, lookback_days=5)

    with state_lock:
        runtime = {
            'active_codes': list(active_stocks.keys()),
            'strategy': get_strategy_snapshot(),
            'risk': copy.deepcopy(risk_state),
            'health': copy.deepcopy(health_state)
        }

    event_counts = debug_summary.get('event_counts', {})
    health_brief = {
        'worker_error': int(event_counts.get('worker_error', 0)),
        'fetch_non_200': int(event_counts.get('fetch_non_200', 0)),
        'signal_rejected': int(event_counts.get('signal_rejected', 0)),
        'risk_guard_triggered': int(event_counts.get('risk_guard_triggered', 0))
    }

    bundle = {
        'date': target_date,
        'generated_at': datetime.datetime.now().isoformat(timespec='seconds'),
        'trigger': trigger,
        'report': report,
        'report_paths': report_paths,
        'debug_summary': debug_summary,
        'health_brief': health_brief,
        'slot_performance': slot_perf,
        'slot_hints': slot_hints,
        'preflight': preflight,
        'latest_tuning': latest_tuning,
        'runtime_snapshot': runtime
    }
    bundle_path = get_daily_bundle_path(target_date)
    with open(bundle_path, 'w', encoding='utf-8') as f:
        json.dump(bundle, f, ensure_ascii=False, indent=2)

    log_debug_event(
        'daily_bundle_generated',
        {
            'date': target_date,
            'trigger': trigger,
            'bundle_path': bundle_path
        },
        target_date=target_date
    )
    return bundle, bundle_path

def build_preflight_assessment(ref_date=None, lookback_days=5):
    ref_date = normalize_date_str(ref_date, fallback_today=True)
    if not ref_date:
        ref_date = datetime.datetime.now().strftime('%Y-%m-%d')
    lookback_days = max(1, min(int(lookback_days), 30))

    conn = get_db()
    rows = conn.execute(
        '''
        SELECT date, total, success, fail, win_rate
        FROM daily_stats
        WHERE date<=?
        ORDER BY date DESC
        LIMIT ?
        ''',
        (ref_date, lookback_days)
    ).fetchall()
    conn.close()

    days = [dict(r) for r in rows]
    total_completed = sum(int(d.get('success', 0)) + int(d.get('fail', 0)) for d in days)
    total_success = sum(int(d.get('success', 0)) for d in days)
    weighted_wr = round(total_success * 100.0 / total_completed, 2) if total_completed > 0 else 0.0
    worst_day_wr = min((float(d.get('win_rate') or 0.0) for d in days), default=0.0)

    slot_perf = compute_slot_performance(days=min(lookback_days, 10), end_date=ref_date)
    slot_hints = build_slot_hints(slot_perf)
    paused, left_sec, reason = is_risk_paused()
    update_health_alerts()
    with state_lock:
        alerts = list(health_state.get('alerts', []))

    level = 'green'
    checklist = []
    if total_completed < 20:
        level = 'yellow'
        checklist.append('近几日有效样本较少，建议继续以模拟为主')
    if weighted_wr < 45:
        level = 'red'
        checklist.append(f'近{lookback_days}日加权胜率偏低({weighted_wr:.1f}%)，不建议直接放大实盘')
    elif weighted_wr < 52 and level != 'red':
        level = 'yellow'
        checklist.append(f'近{lookback_days}日加权胜率一般({weighted_wr:.1f}%)，建议先小资金验证')
    if worst_day_wr < 35:
        level = 'red'
        checklist.append(f'存在极弱交易日(最低日胜率 {worst_day_wr:.1f}%)，应先优化时段模板')
    if paused:
        level = 'red'
        checklist.append(f'风控总闸仍在暂停中({left_sec:.0f}s, {reason})')
    if alerts and level == 'green':
        level = 'yellow'
    if alerts:
        checklist.append(f'运行健康告警 {len(alerts)} 条，建议先排查数据质量')
    if not checklist:
        checklist.append('近几日状态稳定，可进入小仓位实盘观察阶段')

    return {
        'as_of': ref_date,
        'lookback_days': lookback_days,
        'level': level,
        'metrics': {
            'completed': total_completed,
            'weighted_win_rate': weighted_wr,
            'worst_day_win_rate': round(worst_day_wr, 2)
        },
        'daily_stats': days,
        'slot_hints': slot_hints,
        'health_alerts': alerts,
        'risk_pause': {
            'paused': paused,
            'left_sec': round(left_sec, 2),
            'reason': reason
        },
        'checklist': checklist
    }

def generate_daily_report(target_date, trigger='manual'):
    conn = get_db()
    rows = conn.execute(
        '''
        SELECT date, time, seq_no, code, name, type, price, status, resolved_price, gross_profit_pct, profit_pct, desc, resolve_msg, created_at, resolved_at
        FROM signals
        WHERE date=?
        ORDER BY time ASC, created_at ASC
        ''',
        (target_date,)
    ).fetchall()
    conn.close()

    records = [dict(r) for r in rows]
    total = len(records)
    success = sum(1 for r in records if r['status'] == 'success')
    fail = sum(1 for r in records if r['status'] == 'fail')
    pending = sum(1 for r in records if r['status'] == 'pending')
    completed = success + fail
    win_rate = round(success * 100.0 / completed, 2) if completed > 0 else 0.0

    by_type = {}
    for sig_type in ('BUY', 'SELL'):
        subset = [r for r in records if r.get('type') == sig_type]
        s = sum(1 for r in subset if r['status'] == 'success')
        f = sum(1 for r in subset if r['status'] == 'fail')
        c = s + f
        avg_profit = round(sum((r.get('profit_pct') or 0.0) for r in subset if r['status'] in ('success', 'fail')) / c, 4) if c else 0.0
        by_type[sig_type] = {
            'total': len(subset),
            'success': s,
            'fail': f,
            'pending': sum(1 for r in subset if r['status'] == 'pending'),
            'win_rate': round(s * 100.0 / c, 2) if c else 0.0,
            'avg_profit_pct': avg_profit
        }

    by_code_stats = collections.defaultdict(lambda: {'name': '', 'total': 0, 'success': 0, 'fail': 0, 'pending': 0, 'profit_sum': 0.0, 'profit_n': 0})
    for r in records:
        c = r.get('code', '')
        st = by_code_stats[c]
        st['name'] = r.get('name', st['name'])
        st['total'] += 1
        if r['status'] == 'success':
            st['success'] += 1
            st['profit_sum'] += (r.get('profit_pct') or 0.0)
            st['profit_n'] += 1
        elif r['status'] == 'fail':
            st['fail'] += 1
            st['profit_sum'] += (r.get('profit_pct') or 0.0)
            st['profit_n'] += 1
        else:
            st['pending'] += 1

    by_code = []
    for code, st in by_code_stats.items():
        comp = st['success'] + st['fail']
        by_code.append({
            'code': code,
            'name': st['name'],
            'total': st['total'],
            'success': st['success'],
            'fail': st['fail'],
            'pending': st['pending'],
            'win_rate': round(st['success'] * 100.0 / comp, 2) if comp else 0.0,
            'avg_profit_pct': round(st['profit_sum'] / st['profit_n'], 4) if st['profit_n'] else 0.0
        })
    by_code.sort(key=lambda x: x['total'], reverse=True)

    debug_entries = read_debug_log_entries(target_date, limit=50000)
    debug_summary = summarize_debug_entries(debug_entries)
    strategy_snapshot = get_strategy_snapshot()
    report = {
        'date': target_date,
        'generated_at': datetime.datetime.now().isoformat(timespec='seconds'),
        'trigger': trigger,
        'strategy': strategy_snapshot,
        'totals': {
            'total': total,
            'success': success,
            'fail': fail,
            'pending': pending,
            'completed': completed,
            'win_rate': win_rate
        },
        'by_type': by_type,
        'by_code': by_code,
        'debug_summary': debug_summary
    }

    paths = get_daily_report_paths(target_date)
    with open(paths['json'], 'w', encoding='utf-8') as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    top_reasons = sorted(debug_summary['reject_reasons'].items(), key=lambda x: x[1], reverse=True)[:10]
    lines = [
        f"# 日报 {target_date}",
        "",
        f"- 生成时间: {report['generated_at']}",
        f"- 触发方式: {trigger}",
        "",
        "## 总览",
        f"- 信号总数: {total}",
        f"- 已完成: {completed} (成功 {success} / 失败 {fail})",
        f"- 挂单: {pending}",
        f"- 胜率: {win_rate:.2f}%",
        "",
        "## 分方向",
    ]
    for k, v in by_type.items():
        lines.append(
            f"- {k}: total={v['total']}, win_rate={v['win_rate']:.2f}%, pending={v['pending']}, avg_profit_pct={v['avg_profit_pct']:.4f}"
        )
    lines.extend(["", "## 分股票"])
    for item in by_code:
        lines.append(
            f"- {item['code']} {item['name']}: total={item['total']}, win_rate={item['win_rate']:.2f}%, pending={item['pending']}, avg_profit_pct={item['avg_profit_pct']:.4f}"
        )
    lines.extend(["", "## 信号过滤（Top Rejections）"])
    if top_reasons:
        for reason, cnt in top_reasons:
            lines.append(f"- {reason}: {cnt}")
    else:
        lines.append("- 无")

    with open(paths['md'], 'w', encoding='utf-8') as f:
        f.write("\n".join(lines) + "\n")

    log_debug_event(
        'daily_report_generated',
        {
            'date': target_date,
            'trigger': trigger,
            'json_path': paths['json'],
            'md_path': paths['md'],
            'totals': report['totals']
        },
        target_date=target_date
    )
    return report, paths

def read_daily_report_json(target_date):
    path = get_daily_report_paths(target_date)['json']
    if not os.path.exists(path):
        return None
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return None

def get_or_generate_daily_report(target_date, trigger='auto'):
    report = read_daily_report_json(target_date)
    paths = get_daily_report_paths(target_date)
    if report is None:
        report, paths = generate_daily_report(target_date, trigger=trigger)
    return report, paths

def compare_reports(current_report, baseline_report):
    def diff(a, b):
        return round(float(a) - float(b), 4)

    cur_tot = current_report.get('totals', {})
    base_tot = baseline_report.get('totals', {})
    totals_diff = {k: diff(cur_tot.get(k, 0), base_tot.get(k, 0)) for k in ('total', 'success', 'fail', 'pending', 'completed', 'win_rate')}

    type_diff = {}
    cur_type = current_report.get('by_type', {})
    base_type = baseline_report.get('by_type', {})
    for t in set(list(cur_type.keys()) + list(base_type.keys())):
        c = cur_type.get(t, {})
        b = base_type.get(t, {})
        type_diff[t] = {k: diff(c.get(k, 0), b.get(k, 0)) for k in ('total', 'success', 'fail', 'pending', 'win_rate', 'avg_profit_pct')}

    cur_rej = current_report.get('debug_summary', {}).get('reject_reasons', {})
    base_rej = baseline_report.get('debug_summary', {}).get('reject_reasons', {})
    reason_diff = {}
    for k in set(list(cur_rej.keys()) + list(base_rej.keys())):
        reason_diff[k] = int(cur_rej.get(k, 0)) - int(base_rej.get(k, 0))
    reason_diff = dict(sorted(reason_diff.items(), key=lambda x: abs(x[1]), reverse=True)[:15])

    return {
        'totals_diff': totals_diff,
        'by_type_diff': type_diff,
        'reject_reason_diff': reason_diff
    }

def build_param_suggestion(target_date, baseline_date=None):
    report, _ = get_or_generate_daily_report(target_date, trigger='suggestion')
    baseline_report = None
    if baseline_date:
        baseline_report, _ = get_or_generate_daily_report(baseline_date, trigger='suggestion_baseline')

    strategy = report.get('strategy') or get_strategy_snapshot()
    totals = report.get('totals', {})
    by_type = report.get('by_type', {})
    reject = report.get('debug_summary', {}).get('reject_reasons', {})

    patch = {}
    reasons = []

    buy = by_type.get('BUY', {})
    sell = by_type.get('SELL', {})
    buy_total = int(buy.get('total', 0))
    sell_total = int(sell.get('total', 0))
    buy_wr = float(buy.get('win_rate', 0.0))
    sell_wr = float(sell.get('win_rate', 0.0))
    overall_wr = float(totals.get('win_rate', 0.0))
    completed = int(totals.get('completed', 0))

    # BUY 低胜率时提高门槛+更严格确认
    if buy_total >= 8 and buy_wr < 35:
        patch['buy_min_score'] = min(0.80, float(strategy.get('buy_min_score', 0.58)) + 0.02)
        patch['buy_require_confirmation'] = True
        patch['buy_reject_bearish_tape'] = True
        reasons.append(f"BUY 胜率偏低({buy_wr:.1f}%)，上调 buy_min_score 并强化确认")

    # SELL 低胜率时提高 SELL 分数门槛
    if sell_total >= 8 and sell_wr < 45:
        patch['sell_min_score'] = min(0.80, float(strategy.get('sell_min_score', 0.55)) + 0.02)
        reasons.append(f"SELL 胜率偏低({sell_wr:.1f}%)，上调 sell_min_score")

    # 若大量因“买入缺确认”被拒，可微降 BUY 门槛以平衡触发率
    missing_conf = int(reject.get('buy_missing_confirmation', 0))
    if missing_conf >= 15 and buy_wr >= 45:
        patch['buy_min_score'] = max(0.50, float(strategy.get('buy_min_score', 0.58)) - 0.01)
        reasons.append("buy_missing_confirmation 拒绝过多且 BUY 表现不差，微降 buy_min_score 以提高触发率")

    # 总体表现较差时收紧风控
    if completed >= 20 and overall_wr < 45:
        patch['risk_max_consecutive_fail'] = min(int(strategy.get('risk_max_consecutive_fail', 4)), 3)
        patch['risk_pause_minutes'] = max(int(strategy.get('risk_pause_minutes', 30)), 45)
        reasons.append(f"整体胜率偏低({overall_wr:.1f}%)，缩紧连败阈值并延长暂停时间")

    # 若本日低于昨日明显，进一步收紧 BUY
    compare = None
    if baseline_report:
        compare = compare_reports(report, baseline_report)
        win_drop = compare['totals_diff'].get('win_rate', 0)
        if win_drop <= -8:
            patch['buy_min_score'] = min(0.82, max(float(patch.get('buy_min_score', strategy.get('buy_min_score', 0.58))), float(strategy.get('buy_min_score', 0.58)) + 0.02))
            reasons.append(f"较基准日胜率下降 {abs(win_drop):.1f}pct，额外收紧 BUY 门槛")

    # 没有明确建议时给出保持策略
    if not patch:
        reasons.append("当前样本下未发现明显参数漂移，建议保持现有参数并继续观察")

    return {
        'date': target_date,
        'baseline_date': baseline_date,
        'generated_at': datetime.datetime.now().isoformat(timespec='seconds'),
        'strategy_before': strategy,
        'proposed_patch': patch,
        'reasons': reasons,
        'metrics': {
            'overall_win_rate': overall_wr,
            'buy_win_rate': buy_wr,
            'sell_win_rate': sell_wr,
            'completed': completed
        },
        'compare': compare
    }

def normalize_date_str(date_str, fallback_today=False):
    if not date_str:
        return datetime.datetime.now().strftime('%Y-%m-%d') if fallback_today else None
    try:
        return datetime.datetime.strptime(str(date_str), '%Y-%m-%d').strftime('%Y-%m-%d')
    except Exception:
        return None

def get_default_baseline_date(target_date):
    try:
        d = datetime.datetime.strptime(target_date, '%Y-%m-%d').date()
    except Exception:
        d = datetime.datetime.now().date()
    d = d - datetime.timedelta(days=1)
    d = get_previous_trading_day(d)
    return d.strftime('%Y-%m-%d')

def save_tuning_suggestion(suggestion):
    os.makedirs(TUNING_DIR, exist_ok=True)
    now_tag = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
    date_tag = suggestion.get('date') or datetime.datetime.now().strftime('%Y-%m-%d')
    path = os.path.join(TUNING_DIR, f'{date_tag}_{now_tag}.json')
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(suggestion, f, ensure_ascii=False, indent=2)
    return path

def parse_desc_factors(desc):
    text = str(desc or '')
    if not text:
        return []
    m = re.search(r'\]\s*(.*)$', text)
    tail = m.group(1) if m else text
    factors = [x.strip() for x in tail.split('|') if x.strip()]
    return factors

def parse_iso_ts(ts_str):
    if not ts_str:
        return None
    try:
        return datetime.datetime.fromisoformat(str(ts_str)).timestamp()
    except Exception:
        return None

def build_signal_explanation(sig_row):
    signal = dict(sig_row)
    sig_id = signal.get('id')
    sig_date = signal.get('date') or datetime.datetime.now().strftime('%Y-%m-%d')
    code = signal.get('code', '')
    sig_time = signal.get('time', '')
    sig_type = signal.get('type', '')

    debug_entries = read_debug_log_entries(sig_date, limit=50000)
    accepted_evt = None
    resolved_evt = None
    lifecycle = []

    for e in debug_entries:
        if str(e.get('signal_id', '')) == str(sig_id):
            lifecycle.append(e)
            if e.get('event') == 'signal_accepted' and accepted_evt is None:
                accepted_evt = e
            if e.get('event') in ('signal_resolved', 'signal_force_closed') and resolved_evt is None:
                resolved_evt = e

    # 老数据里可能缺 signal_id，退化为同 code+time+type 匹配
    if accepted_evt is None:
        for e in debug_entries:
            if e.get('event') != 'signal_accepted':
                continue
            if str(e.get('code', '')) == str(code) and str(e.get('time', '')) == str(sig_time) and str(e.get('signal_type', '')) == str(sig_type):
                accepted_evt = e
                break
    if resolved_evt is None:
        for e in debug_entries:
            if e.get('event') not in ('signal_resolved', 'signal_force_closed'):
                continue
            if str(e.get('code', '')) == str(code) and str(e.get('time', '')) == str(sig_time) and str(e.get('signal_type', '')) == str(sig_type):
                resolved_evt = e
                break

    filter_meta = (accepted_evt or {}).get('filter_meta') or {}
    factors = (accepted_evt or {}).get('factors') or parse_desc_factors(signal.get('desc', ''))
    slot = filter_meta.get('slot') or get_time_slot_label(sig_time)

    anchor_ts = parse_iso_ts((accepted_evt or {}).get('ts'))
    if anchor_ts is None and sig_time:
        try:
            anchor_ts = datetime.datetime.strptime(f"{sig_date} {sig_time}", "%Y-%m-%d %H:%M:%S").timestamp()
        except Exception:
            anchor_ts = None

    nearby_events = []
    if anchor_ts is not None:
        for e in debug_entries:
            if str(e.get('code', '')) != str(code):
                continue
            ets = parse_iso_ts(e.get('ts'))
            if ets is None:
                continue
            if abs(ets - anchor_ts) <= 300:
                nearby_events.append(e)
    nearby_events = nearby_events[:60]

    with state_lock:
        points = list(market_data.get(code, []))
    chart_points = []
    if points:
        idx = None
        for i, p in enumerate(points):
            if str(p.get('time', '')) == str(sig_time):
                idx = i
                break
        if idx is None:
            idx = len(points) - 1
        lo = max(0, idx - 30)
        hi = min(len(points), idx + 31)
        chart_points = points[lo:hi]

    insights = []
    score = filter_meta.get('score')
    threshold = filter_meta.get('threshold')
    if score is not None and threshold is not None:
        insights.append(f"评分 {float(score):.3f} vs 阈值 {float(threshold):.3f}")
    if sig_type == 'BUY':
        if filter_meta.get('has_bull_tape') or filter_meta.get('has_bull_volume'):
            insights.append('BUY 确认因子存在（盘口或量能）')
        else:
            insights.append('BUY 缺少确认因子，触发质量偏弱')
    if signal.get('status') in ('success', 'fail'):
        insights.append(f"最终 {signal.get('status')}，收益 {float(signal.get('profit_pct') or 0.0):+.2f}%")
    if resolved_evt and resolved_evt.get('event') == 'signal_force_closed':
        insights.append('该信号由收盘强制平仓结束')

    return {
        'signal': signal,
        'slot': slot,
        'factors': factors,
        'filter_meta': filter_meta,
        'strategy_snapshot': (accepted_evt or {}).get('strategy') or get_strategy_snapshot(),
        'accepted_event': accepted_evt,
        'resolved_event': resolved_evt,
        'lifecycle': lifecycle,
        'nearby_events': nearby_events,
        'chart_points': chart_points,
        'insights': insights
    }

def get_previous_trading_day(ref_date):
    d = ref_date
    while d.weekday() >= 5:
        d -= datetime.timedelta(days=1)
    return d

def maybe_auto_generate_daily_report():
    global last_auto_report_date
    now = datetime.datetime.now()

    with state_lock:
        enabled = bool(success_rates.get('auto_daily_report_enabled', True))
    if not enabled:
        return

    target_date = None
    # 工作日收盘后生成当日日报；周末兜底生成最近一个交易日
    if now.weekday() < 5 and (now.hour > 15 or (now.hour == 15 and now.minute >= 5)):
        target_date = now.strftime('%Y-%m-%d')
    elif now.weekday() >= 5:
        d = get_previous_trading_day((now - datetime.timedelta(days=1)).date())
        target_date = d.strftime('%Y-%m-%d')

    if not target_date or target_date == last_auto_report_date:
        return

    conn = get_db()
    cnt = conn.execute('SELECT COUNT(*) AS c FROM signals WHERE date=?', (target_date,)).fetchone()['c']
    conn.close()
    if cnt <= 0:
        return

    generate_daily_report(target_date, trigger='auto_after_close')
    try:
        baseline = get_default_baseline_date(target_date)
        suggestion = build_param_suggestion(target_date, baseline_date=baseline)
        suggestion_path = save_tuning_suggestion(suggestion)
        log_debug_event(
            'tuning_suggested_auto',
            {
                'date': target_date,
                'baseline_date': baseline,
                'path': suggestion_path,
                'proposed_patch': suggestion.get('proposed_patch', {})
            },
            target_date=target_date
        )
    except Exception as e:
        log_debug_event('tuning_suggested_auto_failed', {'date': target_date, 'error': str(e)}, target_date=target_date)
    try:
        generate_daily_bundle(target_date, trigger='auto_after_close')
    except Exception as e:
        log_debug_event('daily_bundle_auto_failed', {'date': target_date, 'error': str(e)}, target_date=target_date)
    last_auto_report_date = target_date

@app.route('/api/debug/logs')
def api_debug_logs():
    date_q = request.args.get('date') or datetime.datetime.now().strftime('%Y-%m-%d')
    try:
        limit = int(request.args.get('limit', 500))
    except Exception:
        limit = 500
    limit = max(1, min(limit, 5000))
    event_q = (request.args.get('event') or '').strip()
    code_q = (request.args.get('code') or '').strip().lower()

    entries = read_debug_log_entries(date_q, limit=limit)
    if event_q:
        entries = [e for e in entries if e.get('event') == event_q]
    if code_q:
        entries = [e for e in entries if str(e.get('code', '')).lower() == code_q]

    return jsonify({
        'date': date_q,
        'count': len(entries),
        'entries': entries
    })

@app.route('/api/debug/summary')
def api_debug_summary():
    date_q = request.args.get('date') or datetime.datetime.now().strftime('%Y-%m-%d')
    entries = read_debug_log_entries(date_q, limit=5000)
    summary = summarize_debug_entries(entries)
    summary['date'] = date_q
    return jsonify(summary)

@app.route('/api/reports/daily')
def api_get_daily_report():
    date_q = request.args.get('date') or datetime.datetime.now().strftime('%Y-%m-%d')
    generate_if_missing = to_bool(request.args.get('generate', '1'))
    report = read_daily_report_json(date_q)
    paths = get_daily_report_paths(date_q)
    if report is None and generate_if_missing:
        report, paths = generate_daily_report(date_q, trigger='api_get_fallback')
    return jsonify({
        'success': report is not None,
        'date': date_q,
        'report': report,
        'json_path': paths['json'],
        'md_path': paths['md']
    })

@app.route('/api/reports/daily/generate', methods=['POST'])
def api_generate_daily_report():
    data = request.get_json(silent=True) or {}
    date_q = data.get('date') or datetime.datetime.now().strftime('%Y-%m-%d')
    report, paths = generate_daily_report(date_q, trigger='api_manual')
    return jsonify({
        'success': True,
        'date': date_q,
        'report': report,
        'json_path': paths['json'],
        'md_path': paths['md']
    })

@app.route('/api/reports/daily/list')
def api_list_daily_reports():
    os.makedirs(REPORT_DIR, exist_ok=True)
    try:
        limit = int(request.args.get('limit', 30))
    except Exception:
        limit = 30
    limit = max(1, min(limit, 365))

    files = [f for f in os.listdir(REPORT_DIR) if f.endswith('.json')]
    files.sort(reverse=True)
    items = []
    for name in files[:limit]:
        date_part = name.replace('.json', '')
        paths = get_daily_report_paths(date_part)
        items.append({
            'date': date_part,
            'json_path': paths['json'],
            'md_path': paths['md'],
            'exists_md': os.path.exists(paths['md'])
        })
    return jsonify({'success': True, 'items': items})

@app.route('/api/reports/daily/bundle')
def api_get_daily_bundle():
    date_q = normalize_date_str(request.args.get('date'), fallback_today=True)
    if not date_q:
        return jsonify({'success': False, 'msg': 'invalid date, expected YYYY-MM-DD'})

    generate_if_missing = to_bool(request.args.get('generate', '1'))
    bundle = read_daily_bundle_json(date_q)
    path = get_daily_bundle_path(date_q)
    if bundle is None and generate_if_missing:
        bundle, path = generate_daily_bundle(date_q, trigger='api_get_bundle')

    return jsonify({
        'success': bundle is not None,
        'date': date_q,
        'bundle': bundle,
        'path': path
    })

@app.route('/api/reports/daily/bundle/generate', methods=['POST'])
def api_generate_daily_bundle():
    data = request.get_json(silent=True) or {}
    date_q = normalize_date_str(data.get('date'), fallback_today=True)
    if not date_q:
        return jsonify({'success': False, 'msg': 'invalid date, expected YYYY-MM-DD'})
    bundle, path = generate_daily_bundle(date_q, trigger='api_manual_bundle')
    return jsonify({
        'success': True,
        'date': date_q,
        'bundle': bundle,
        'path': path
    })

@app.route('/api/reports/daily/compare')
def api_compare_daily_reports():
    date_q = normalize_date_str(request.args.get('date'), fallback_today=True)
    if not date_q:
        return jsonify({'success': False, 'msg': 'invalid date, expected YYYY-MM-DD'})

    baseline_q = normalize_date_str(request.args.get('baseline'))
    if not baseline_q:
        baseline_q = get_default_baseline_date(date_q)

    generate_if_missing = to_bool(request.args.get('generate', '1'))
    current_report = read_daily_report_json(date_q)
    baseline_report = read_daily_report_json(baseline_q)

    if generate_if_missing:
        if current_report is None:
            current_report, _ = get_or_generate_daily_report(date_q, trigger='api_compare_current')
        if baseline_report is None:
            baseline_report, _ = get_or_generate_daily_report(baseline_q, trigger='api_compare_baseline')

    if current_report is None:
        return jsonify({'success': False, 'msg': f'current report not found: {date_q}'})
    if baseline_report is None:
        return jsonify({'success': False, 'msg': f'baseline report not found: {baseline_q}'})

    compare = compare_reports(current_report, baseline_report)
    return jsonify({
        'success': True,
        'date': date_q,
        'baseline_date': baseline_q,
        'current_report': current_report,
        'baseline_report': baseline_report,
        'compare': compare,
        'current_paths': get_daily_report_paths(date_q),
        'baseline_paths': get_daily_report_paths(baseline_q)
    })

@app.route('/api/preflight')
def api_preflight():
    try:
        lookback = int(request.args.get('lookback', 5))
    except Exception:
        lookback = 5
    date_q = request.args.get('date')
    assessment = build_preflight_assessment(ref_date=date_q, lookback_days=lookback)
    return jsonify({'success': True, 'assessment': assessment})

@app.route('/api/analytics/slot-performance')
def api_slot_performance():
    try:
        days = int(request.args.get('days', 10))
    except Exception:
        days = 10
    end_date = request.args.get('date')
    perf = compute_slot_performance(days=days, end_date=end_date)
    hints = build_slot_hints(perf)
    return jsonify({'success': True, 'performance': perf, 'hints': hints})

@app.route('/api/tuning/suggest')
def api_tuning_suggest():
    date_q = normalize_date_str(request.args.get('date'), fallback_today=True)
    if not date_q:
        return jsonify({'success': False, 'msg': 'invalid date, expected YYYY-MM-DD'})

    baseline_q = normalize_date_str(request.args.get('baseline'))
    if not baseline_q:
        baseline_q = get_default_baseline_date(date_q)

    suggestion = build_param_suggestion(date_q, baseline_date=baseline_q)
    suggestion_path = save_tuning_suggestion(suggestion)

    log_debug_event(
        'tuning_suggested',
        {
            'date': date_q,
            'baseline_date': baseline_q,
            'proposed_patch': suggestion.get('proposed_patch', {}),
            'path': suggestion_path
        },
        target_date=date_q
    )
    return jsonify({
        'success': True,
        'date': date_q,
        'baseline_date': baseline_q,
        'suggestion': suggestion,
        'saved_path': suggestion_path
    })

@app.route('/api/tuning/apply', methods=['POST'])
def api_tuning_apply():
    data = request.get_json(silent=True) or {}
    date_q = normalize_date_str(data.get('date'), fallback_today=True)
    if not date_q:
        return jsonify({'success': False, 'msg': 'invalid date, expected YYYY-MM-DD'})

    baseline_q = normalize_date_str(data.get('baseline'))
    if not baseline_q:
        baseline_q = get_default_baseline_date(date_q)

    patch = data.get('patch')
    suggestion = None
    if patch is None:
        suggestion = build_param_suggestion(date_q, baseline_date=baseline_q)
        patch = suggestion.get('proposed_patch', {})

    if not isinstance(patch, dict):
        return jsonify({'success': False, 'msg': 'patch must be object'})

    if not patch:
        return jsonify({
            'success': False,
            'msg': 'no patch to apply',
            'date': date_q,
            'baseline_date': baseline_q,
            'suggestion': suggestion
        })

    ok, errors, applied = apply_strategy_patch(patch)
    if not ok:
        return jsonify({'success': False, 'msg': 'invalid patch', 'errors': errors})

    save_snapshot = to_bool(data.get('save_snapshot', True))
    snapshot_id = None
    if save_snapshot:
        note = data.get('note') or f"tuning_apply {date_q} vs {baseline_q}"
        snapshot_id, _ = save_param_version(note=note)

    log_debug_event(
        'tuning_applied',
        {
            'date': date_q,
            'baseline_date': baseline_q,
            'applied_patch': applied,
            'snapshot_id': snapshot_id,
            'strategy': get_strategy_snapshot()
        },
        target_date=date_q
    )
    return jsonify({
        'success': True,
        'date': date_q,
        'baseline_date': baseline_q,
        'applied': applied,
        'snapshot_id': snapshot_id,
        'strategy_after': get_strategy_snapshot(),
        'suggestion': suggestion
    })

@app.route('/api/tuning/history')
def api_tuning_history():
    os.makedirs(TUNING_DIR, exist_ok=True)
    try:
        limit = int(request.args.get('limit', 30))
    except Exception:
        limit = 30
    limit = max(1, min(limit, 365))

    files = [f for f in os.listdir(TUNING_DIR) if f.endswith('.json')]
    files.sort(reverse=True)
    items = []
    for name in files[:limit]:
        path = os.path.join(TUNING_DIR, name)
        item = {
            'file': name,
            'path': path
        }
        try:
            with open(path, 'r', encoding='utf-8') as f:
                payload = json.load(f)
            item['date'] = payload.get('date')
            item['baseline_date'] = payload.get('baseline_date')
            item['generated_at'] = payload.get('generated_at')
            item['patch_size'] = len((payload.get('proposed_patch') or {}))
        except Exception:
            pass
        items.append(item)
    return jsonify({'success': True, 'items': items})

@app.route('/api/signals/<sig_id>/explain')
def api_signal_explain(sig_id):
    conn = get_db()
    row = conn.execute(
        '''
        SELECT id, date, time, seq_no, code, name, type, level, price, desc, status, resolved_price, gross_profit_pct, profit_pct, resolve_msg, created_at, resolved_at
        FROM signals
        WHERE id=?
        ''',
        (sig_id,)
    ).fetchone()
    conn.close()
    if not row:
        return jsonify({'success': False, 'msg': f'signal not found: {sig_id}'})

    explain = build_signal_explanation(row)
    return jsonify({
        'success': True,
        'signal_id': sig_id,
        'explain': explain
    })

if __name__ == '__main__':
    # 启动时恢复今日信号
    restored = load_today_signals()
    if restored:
        signals_history = restored
        today_stats_conn = get_db()
        today = datetime.datetime.now().strftime('%Y-%m-%d')
        row = today_stats_conn.execute('SELECT * FROM daily_stats WHERE date=?', (today,)).fetchone()
        if row:
            success_rates['total'] = row['total']
            success_rates['success'] = row['success']
            success_rates['fail'] = row['fail']
            
        # 恢复个股胜率统计
        for sig in restored:
            if sig['status'] in ['success', 'fail']:
                c = sig.get('code', '')
                if c not in success_rates['stocks']:
                    success_rates['stocks'][c] = {'success': 0, 'fail': 0}
                success_rates['stocks'][c][sig['status']] += 1
                
        today_stats_conn.close()
        pending_signals = [s for s in restored if s['status'] == 'pending']
        success_rates['pending'] = len(pending_signals)
        print(f"📂 已恢复今日 {len(restored)} 条信号记录 ({len(pending_signals)} 条待处理)")
    init_risk_state_from_db()
    log_debug_event(
        'app_started',
        {
            'restored_signals': len(restored),
            'pending': len(pending_signals),
            'active_codes': list(active_stocks.keys()),
            'strategy': get_strategy_snapshot()
        }
    )
    
    print("🚀 启动人福医药量化策略多只自选版 Web 端...")
    t = threading.Thread(target=fetch_worker, daemon=True)
    t.start()
    app.run(port=8080, host='0.0.0.0', debug=False)
