import datetime
import os


def _prime_market_state(app_module):
    with app_module.state_lock:
        app_module.active_stocks.clear()
        app_module.market_data.clear()
        app_module.signals_history.clear()
        app_module.pending_signals.clear()
        app_module.stock_contexts.clear()
        app_module.stock_extras.clear()
        app_module.success_rates['stocks'] = {}

        app_module.active_stocks['sh600079'] = '测试股票'
        app_module.market_data['sh600079'] = [
            {'time': '09:30:00', 'price': 10.00, 'vwap': 10.00, 'ts': 100.0},
            {'time': '09:31:00', 'price': 10.12, 'vwap': 10.06, 'ts': 200.0},
        ]
        app_module.stock_extras['sh600079'] = {'yest_close': 9.90, 'open_price': 10.00}


def test_parse_since_ts_arg_supports_seconds_and_milliseconds(load_app):
    app_module = load_app()
    assert app_module.parse_since_ts_arg('1700000000') == 1700000000.0
    assert app_module.parse_since_ts_arg('1700000000000') == 1700000000.0
    assert app_module.parse_since_ts_arg('') is None
    assert app_module.parse_since_ts_arg('not-a-number') is None


def test_default_focus_stock_and_limit(load_app):
    app_module = load_app()
    assert app_module.FOCUS_STOCK_CODE == 'sz002438'
    assert app_module.FOCUS_STOCK_NAME == '江苏神通'
    assert app_module.MAX_STOCKS == 3
    assert app_module.DEFAULT_WATCHLIST == ['sz002438']
    assert app_module.get_stock_signal_profile('sz002438')['name'] == 'jsst_intraday_t_v1'
    assert app_module.get_time_slot_templates_for_code('sz002438')['open']['buy_min_score'] == 0.64


def test_apply_add_stock_rejects_when_already_at_three(load_app):
    app_module = load_app()
    with app_module.state_lock:
        app_module.active_stocks.clear()
        app_module.active_stocks['sz002438'] = '江苏神通'
        app_module.active_stocks['sh600079'] = '人福医药'
        app_module.active_stocks['sz300402'] = '宝色股份'

    ok, msg = app_module.apply_add_stock('sz000001')
    assert ok is False
    assert '最多只能监控 3 只股票' in msg


def test_each_stock_can_have_dedicated_strategy_patch(load_app):
    app_module = load_app()

    class DummyAnalyzer:
        def __init__(self):
            self.profile = {}

    with app_module.state_lock:
        app_module.analyzers['sz002438'] = DummyAnalyzer()

    ok, errors, applied = app_module.apply_strategy_patch({
        'stock_strategies': {
            'sz002438': {
                'buy_min_score': 0.71,
                'trade_cost_buffer': 0.0030,
                'time_slot_templates': {
                    'open': {'buy_min_score': 0.73}
                },
                'signal_profile': {
                    'name': 'jsst_custom_v1',
                    'signal_threshold': 0.61,
                    'edge_min': 0.19
                }
            }
        }
    })

    assert ok is True
    assert errors == {}
    assert applied['stock_strategies']['sz002438']['buy_min_score'] == 0.71

    snapshot = app_module.get_strategy_snapshot()
    stock_cfg = snapshot['stock_strategies']['sz002438']
    assert stock_cfg['buy_min_score'] == 0.71
    assert stock_cfg['signal_profile']['name'] == 'jsst_custom_v1'

    effective_open = app_module.get_effective_strategy('09:35:00', code='sz002438')
    effective_morning = app_module.get_effective_strategy('10:05:00', code='sz002438')
    assert effective_open['buy_min_score'] == 0.73
    assert effective_morning['buy_min_score'] == 0.73
    assert effective_morning['trade_cost_buffer'] == 0.003

    gross, net, final = app_module.classify_trade_result('BUY', 100.0, 100.2, code='sz002438')
    assert round(gross, 6) == 0.002
    assert round(net, 6) == -0.001
    assert final == 'fail'

    profile = app_module.get_stock_signal_profile('sz002438')
    assert profile['signal_threshold'] == 0.61
    assert profile['edge_min'] == 0.19
    assert app_module.analyzers['sz002438'].profile['signal_threshold'] == 0.61


def test_new_stock_gets_dedicated_strategy_record(load_app):
    app_module = load_app()

    cfg = app_module.ensure_stock_strategy('sz000001')

    assert isinstance(cfg, dict)
    assert isinstance(cfg.get('time_slot_templates'), dict)
    assert isinstance(cfg.get('signal_profile'), dict)
    assert cfg['signal_profile']['name']

    snapshot = app_module.get_strategy_snapshot()
    assert 'sz000001' in snapshot['stock_strategies']


def test_api_data_full_and_delta_sync(load_app):
    app_module = load_app()
    _prime_market_state(app_module)
    client = app_module.app.test_client()

    full_resp = client.get('/api/data?full=1')
    assert full_resp.status_code == 200
    full_data = full_resp.get_json()
    assert full_data['mode'] == 'full'
    assert full_data['success'] is True
    assert len(full_data['market_data']['sh600079']) == 2

    delta_resp = client.get('/api/data?since_ts=150')
    assert delta_resp.status_code == 200
    delta_data = delta_resp.get_json()
    assert delta_data['mode'] == 'delta'
    assert len(delta_data['market_data']['sh600079']) == 1
    assert delta_data['market_data']['sh600079'][0]['time'] == '09:31:00'


def test_write_api_auth_enforced_when_token_configured(load_app):
    app_module = load_app(api_token='secret-token')
    client = app_module.app.test_client()

    denied = client.post('/api/config', json={})
    assert denied.status_code == 401

    allowed = client.post(
        '/api/config',
        json={},
        headers={'X-API-Token': 'secret-token'}
    )
    assert allowed.status_code == 200
    assert allowed.get_json().get('success') is True


def test_classify_trade_result_uses_cost_buffer(load_app):
    app_module = load_app()
    with app_module.state_lock:
        app_module.success_rates['trade_cost_buffer'] = 0.0012

    gross, net, final = app_module.classify_trade_result('BUY', 100.0, 100.1)
    assert round(gross, 6) == 0.001
    assert round(net, 6) == -0.0002
    assert final == 'fail'


def test_risk_guard_pause_triggered_by_consecutive_failures(load_app):
    app_module = load_app()
    today = datetime.datetime.now().strftime('%Y-%m-%d')
    with app_module.state_lock:
        app_module.success_rates['risk_guard_enabled'] = True
        app_module.success_rates['risk_max_consecutive_fail'] = 2
        app_module.success_rates['risk_pause_minutes'] = 1
        app_module.success_rates['risk_daily_profit_floor'] = -99.0
    app_module.reset_risk_state_for_day(today)

    sample_sig = {'id': 'sig-demo', 'time': '10:00:00', 'profit_pct': -0.5}
    app_module.update_risk_state_on_resolution(sample_sig, 'fail')
    app_module.update_risk_state_on_resolution(sample_sig, 'fail')

    paused, _, reason = app_module.is_risk_paused()
    assert paused is True
    assert reason == 'max_consecutive_fail_reached'


def test_should_accept_signal_blocks_open_slot_when_enabled(load_app):
    app_module = load_app()
    with app_module.state_lock:
        app_module.success_rates['risk_block_open_slot'] = True
        app_module.success_rates['risk_block_close_slot'] = False

    accepted, reasons, meta = app_module.should_accept_signal(
        'sh600079',
        {'type': 'BUY', 'time': '09:35:00', 'bull_score': 0.9, 'bear_score': 0.1, 'factors': []}
    )
    assert accepted is False
    assert 'risk_slot_block_open' in reasons
    assert meta.get('slot') == 'open'


def test_focus_guard_blocks_weak_focus_buy_slot(load_app):
    app_module = load_app()
    conn = app_module.get_db()
    rows = [
        ('fg1', '2026-03-07', '10:02:00', 1, 'sz002438', '江苏神通', 'BUY', 1, 10.0, 'd', 'fail', -0.8),
        ('fg2', '2026-03-07', '10:06:00', 2, 'sz002438', '江苏神通', 'BUY', 1, 10.0, 'd', 'fail', -0.5),
        ('fg3', '2026-03-07', '10:10:00', 3, 'sz002438', '江苏神通', 'BUY', 1, 10.0, 'd', 'fail', -0.4),
        ('fg4', '2026-03-07', '10:14:00', 4, 'sz002438', '江苏神通', 'BUY', 1, 10.0, 'd', 'success', 0.2),
        ('fg5', '2026-03-07', '13:35:00', 5, 'sz002438', '江苏神通', 'SELL', 1, 10.0, 'd', 'success', 0.7),
        ('fg6', '2026-03-07', '14:10:00', 6, 'sz002438', '江苏神通', 'SELL', 1, 10.0, 'd', 'success', 0.5),
    ]
    conn.executemany(
        """
        INSERT INTO signals (id, date, time, seq_no, code, name, type, level, price, desc, status, profit_pct)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        rows
    )
    conn.commit()
    conn.close()

    with app_module.state_lock:
        app_module.success_rates['risk_block_open_slot'] = False
        app_module.success_rates['risk_block_close_slot'] = False
        app_module.success_rates['regime_filter_enabled'] = False
        app_module.success_rates['buy_require_confirmation'] = False
        app_module.success_rates['buy_reject_bearish_tape'] = False
        app_module.success_rates['focus_guard_enabled'] = True

    accepted, reasons, meta = app_module.should_accept_signal(
        'sz002438',
        {'type': 'BUY', 'date': '2026-03-07', 'time': '10:20:00', 'bull_score': 0.95, 'bear_score': 0.1, 'factors': []}
    )

    assert accepted is False
    assert ('focus_guard_weak_side' in reasons) or ('focus_guard_weak_slot' in reasons) or ('focus_guard_weak_slot_side' in reasons)
    assert meta.get('focus_guard_meta', {}).get('active') is True
    assert meta.get('focus_guard_meta', {}).get('completed') == 6


def test_focus_guard_skips_when_focus_samples_insufficient(load_app):
    app_module = load_app()
    conn = app_module.get_db()
    rows = [
        ('fh1', '2026-03-07', '10:02:00', 1, 'sz002438', '江苏神通', 'BUY', 1, 10.0, 'd', 'fail', -0.8),
        ('fh2', '2026-03-07', '10:06:00', 2, 'sz002438', '江苏神通', 'BUY', 1, 10.0, 'd', 'success', 0.5),
        ('fh3', '2026-03-07', '13:35:00', 3, 'sz002438', '江苏神通', 'SELL', 1, 10.0, 'd', 'success', 0.7),
        ('fh4', '2026-03-07', '14:10:00', 4, 'sz002438', '江苏神通', 'SELL', 1, 10.0, 'd', 'success', 0.5),
    ]
    conn.executemany(
        """
        INSERT INTO signals (id, date, time, seq_no, code, name, type, level, price, desc, status, profit_pct)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        rows
    )
    conn.commit()
    conn.close()

    with app_module.state_lock:
        app_module.success_rates['risk_block_open_slot'] = False
        app_module.success_rates['risk_block_close_slot'] = False
        app_module.success_rates['regime_filter_enabled'] = False
        app_module.success_rates['buy_require_confirmation'] = False
        app_module.success_rates['buy_reject_bearish_tape'] = False
        app_module.success_rates['focus_guard_enabled'] = True

    accepted, reasons, meta = app_module.should_accept_signal(
        'sz002438',
        {'type': 'BUY', 'date': '2026-03-07', 'time': '10:20:00', 'bull_score': 0.95, 'bear_score': 0.1, 'factors': []}
    )

    assert accepted is True
    assert reasons == []
    assert meta.get('focus_guard_meta', {}).get('insufficient_samples') is True


def test_focus_side_cooldown_blocks_same_side_only(load_app):
    app_module = load_app()
    today = datetime.datetime.now().strftime('%Y-%m-%d')
    conn = app_module.get_db()
    rows = [
        ('fc1', today, '10:01:00', 1, 'sz002438', '江苏神通', 'BUY', 1, 10.0, 'd', 'fail', -0.7),
        ('fc2', today, '10:05:00', 2, 'sz002438', '江苏神通', 'BUY', 1, 10.0, 'd', 'fail', -0.4),
        ('fc3', today, '10:11:00', 3, 'sz002438', '江苏神通', 'BUY', 1, 10.0, 'd', 'success', 0.4),
        ('fc4', today, '10:18:00', 4, 'sz002438', '江苏神通', 'BUY', 1, 10.0, 'd', 'fail', -0.3),
    ]
    conn.executemany(
        """
        INSERT INTO signals (id, date, time, seq_no, code, name, type, level, price, desc, status, profit_pct)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        rows
    )
    conn.commit()
    conn.close()

    with app_module.state_lock:
        app_module.success_rates['risk_block_open_slot'] = False
        app_module.success_rates['risk_block_close_slot'] = False
        app_module.success_rates['regime_filter_enabled'] = False
        app_module.success_rates['buy_require_confirmation'] = False
        app_module.success_rates['buy_reject_bearish_tape'] = False
        app_module.success_rates['focus_guard_enabled'] = True
    app_module.reset_risk_state_for_day(today)

    app_module.update_risk_state_on_resolution(
        {'id': 'live1', 'code': 'sz002438', 'type': 'BUY', 'date': today, 'time': '10:26:00', 'profit_pct': -0.6},
        'fail'
    )
    app_module.update_risk_state_on_resolution(
        {'id': 'live2', 'code': 'sz002438', 'type': 'BUY', 'date': today, 'time': '10:33:00', 'profit_pct': -0.5},
        'fail'
    )

    paused, left_sec, reason = app_module.is_focus_side_paused('sz002438', 'BUY')
    assert paused is True
    assert left_sec > 0
    assert reason == 'focus_side_fail_streak'

    accepted_buy, buy_reasons, buy_meta = app_module.should_accept_signal(
        'sz002438',
        {'type': 'BUY', 'date': today, 'time': '10:36:00', 'bull_score': 0.95, 'bear_score': 0.1, 'factors': []}
    )
    assert accepted_buy is False
    assert 'focus_side_cooled_down' in buy_reasons
    assert buy_meta.get('focus_side_pause_left_sec', 0) > 0

    accepted_sell, sell_reasons, sell_meta = app_module.should_accept_signal(
        'sz002438',
        {'type': 'SELL', 'date': today, 'time': '10:36:00', 'bull_score': 0.1, 'bear_score': 0.95, 'factors': []}
    )
    assert accepted_sell is True
    assert sell_reasons == []
    assert sell_meta.get('focus_guard_meta', {}).get('active') is True


def test_build_data_payload_includes_focus_guard_status(load_app):
    app_module = load_app()
    today = datetime.datetime.now().strftime('%Y-%m-%d')
    conn = app_module.get_db()
    rows = [
        ('fd1', today, '10:01:00', 1, 'sz002438', '江苏神通', 'BUY', 1, 10.0, 'd', 'fail', -0.7),
        ('fd2', today, '10:05:00', 2, 'sz002438', '江苏神通', 'BUY', 1, 10.0, 'd', 'fail', -0.4),
        ('fd3', today, '10:11:00', 3, 'sz002438', '江苏神通', 'BUY', 1, 10.0, 'd', 'success', 0.4),
        ('fd4', today, '10:18:00', 4, 'sz002438', '江苏神通', 'BUY', 1, 10.0, 'd', 'fail', -0.3),
        ('fd5', today, '13:35:00', 5, 'sz002438', '江苏神通', 'SELL', 1, 10.0, 'd', 'success', 0.7),
        ('fd6', today, '14:10:00', 6, 'sz002438', '江苏神通', 'SELL', 1, 10.0, 'd', 'success', 0.5),
    ]
    conn.executemany(
        """
        INSERT INTO signals (id, date, time, seq_no, code, name, type, level, price, desc, status, profit_pct)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        rows
    )
    conn.commit()
    conn.close()

    with app_module.state_lock:
        app_module.success_rates['focus_guard_enabled'] = True
    app_module.reset_risk_state_for_day(today)
    app_module.update_risk_state_on_resolution(
        {'id': 'live3', 'code': 'sz002438', 'type': 'BUY', 'date': today, 'time': '10:26:00', 'profit_pct': -0.6},
        'fail'
    )
    app_module.update_risk_state_on_resolution(
        {'id': 'live4', 'code': 'sz002438', 'type': 'BUY', 'date': today, 'time': '10:33:00', 'profit_pct': -0.5},
        'fail'
    )

    payload = app_module.build_data_payload(force_full=True)
    focus_guard = payload['focus_guard']

    assert focus_guard['code'] == 'sz002438'
    assert focus_guard['enabled'] is True
    assert focus_guard['completed'] >= 6
    assert focus_guard['cooldowns']['BUY']['paused'] is True
    assert focus_guard['cooldowns']['BUY']['left_sec'] > 0
    assert focus_guard['stage'] in ('cooldown', 'guarded')


def test_build_data_payload_includes_rejection_monitor(load_app):
    app_module = load_app()
    today = datetime.datetime.now().strftime('%Y-%m-%d')

    app_module.log_debug_event(
        'signal_accepted',
        {
            'date': today,
            'code': 'sz002438',
            'name': '江苏神通',
            'signal_type': 'BUY'
        },
        target_date=today
    )
    app_module.log_debug_event(
        'signal_rejected',
        {
            'date': today,
            'code': 'sz002438',
            'name': '江苏神通',
            'signal_type': 'BUY',
            'reasons': ['focus_guard_weak_slot']
        },
        target_date=today
    )
    app_module.log_debug_event(
        'signal_rejected',
        {
            'date': today,
            'code': 'sz002438',
            'name': '江苏神通',
            'signal_type': 'SELL',
            'reasons': ['focus_guard_weak_slot']
        },
        target_date=today
    )
    app_module.log_debug_event(
        'signal_rejected',
        {
            'date': today,
            'code': 'sh600079',
            'name': '测试股票',
            'signal_type': 'BUY',
            'reasons': ['risk_slot_block_open']
        },
        target_date=today
    )

    payload = app_module.build_data_payload(force_full=True)
    monitor = payload['rejection_monitor']

    assert monitor['focus_code'] == 'sz002438'
    assert monitor['overall']['rejected'] == 3
    assert monitor['overall']['accepted'] == 1
    assert monitor['focus']['rejected'] == 2
    assert monitor['focus']['accepted'] == 1
    assert monitor['focus']['buy_rejected'] == 1
    assert monitor['focus']['sell_rejected'] == 1
    assert monitor['focus']['top_reasons'][0]['reason'] == 'focus_guard_weak_slot'
    assert monitor['focus']['top_reasons'][0]['count'] == 2
    assert monitor['focus_sides']['BUY']['stage'] in ('normal', 'watch')
    assert monitor['focus_sides']['BUY']['recent_total'] >= 1
    assert monitor['stage'] in ('normal', 'watch')


def test_build_data_payload_marks_hot_focus_side_pressure(load_app):
    app_module = load_app()
    today = datetime.datetime.now().strftime('%Y-%m-%d')

    app_module.log_debug_event(
        'signal_accepted',
        {
            'date': today,
            'code': 'sz002438',
            'name': '江苏神通',
            'signal_type': 'BUY'
        },
        target_date=today
    )
    for idx in range(3):
        app_module.log_debug_event(
            'signal_rejected',
            {
                'date': today,
                'code': 'sz002438',
                'name': '江苏神通',
                'signal_type': 'BUY',
                'reasons': ['focus_side_pressure_tightening']
            },
            target_date=today
        )

    payload = app_module.build_data_payload(force_full=True)
    monitor = payload['rejection_monitor']
    buy_side = monitor['focus_sides']['BUY']

    assert buy_side['stage'] == 'hot'
    assert buy_side['recent_total'] == 4
    assert buy_side['recent_reject_rate'] == 75.0
    assert buy_side['threshold_add'] == 0.04
    assert any(item['side'] == 'BUY' for item in monitor['pressure_alerts'])
    assert monitor['stage'] == 'hot'



def test_should_accept_signal_tightens_focus_buy_threshold_when_pressure_hot(load_app):
    app_module = load_app()
    today = datetime.datetime.now().strftime('%Y-%m-%d')

    with app_module.state_lock:
        app_module.success_rates['risk_block_open_slot'] = False
        app_module.success_rates['risk_block_close_slot'] = False
        app_module.success_rates['regime_filter_enabled'] = False
        app_module.success_rates['buy_require_confirmation'] = False
        app_module.success_rates['buy_reject_bearish_tape'] = False
        app_module.success_rates['focus_guard_enabled'] = True

    app_module.log_debug_event(
        'signal_accepted',
        {
            'date': today,
            'code': 'sz002438',
            'name': '江苏神通',
            'signal_type': 'BUY'
        },
        target_date=today
    )
    for idx in range(3):
        app_module.log_debug_event(
            'signal_rejected',
            {
                'date': today,
                'code': 'sz002438',
                'name': '江苏神通',
                'signal_type': 'BUY',
                'reasons': ['focus_guard_weak_slot']
            },
            target_date=today
        )

    base_threshold = float(app_module.get_effective_strategy('10:20:00', code='sz002438')['buy_min_score'])
    score = round(base_threshold + 0.01, 4)

    accepted, reasons, meta = app_module.should_accept_signal(
        'sz002438',
        {'type': 'BUY', 'date': today, 'time': '10:20:00', 'bull_score': score, 'bear_score': 0.1, 'factors': []}
    )

    assert accepted is False
    assert 'focus_side_pressure_tightening' in reasons
    assert any(reason.startswith('buy_score<') for reason in reasons)
    assert meta['base_threshold'] == round(base_threshold, 4)
    assert meta['threshold_add'] == 0.04
    assert meta['threshold'] == round(base_threshold + 0.04, 4)
    assert meta['pressure_meta']['stage'] == 'hot'


def test_build_data_payload_includes_focus_review(load_app):
    app_module = load_app()
    today = datetime.datetime.now().strftime('%Y-%m-%d')
    conn = app_module.get_db()
    rows = [
        ('fr1', today, '09:42:00', 1, 'sz002438', '江苏神通', 'BUY', 1, 10.0, 'd', 'success', 0.8),
        ('fr2', today, '10:18:00', 2, 'sz002438', '江苏神通', 'BUY', 1, 10.0, 'd', 'fail', -0.5),
        ('fr3', today, '13:36:00', 3, 'sz002438', '江苏神通', 'SELL', 1, 10.0, 'd', 'success', 0.6),
        ('fr4', today, '14:42:00', 4, 'sz002438', '江苏神通', 'SELL', 1, 10.0, 'd', 'fail', -0.3),
    ]
    conn.executemany(
        """
        INSERT INTO signals (id, date, time, seq_no, code, name, type, level, price, desc, status, profit_pct)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        rows
    )
    conn.commit()
    conn.close()

    payload = app_module.build_data_payload(force_full=True)
    review = payload['focus_review']

    assert review['code'] == 'sz002438'
    assert review['name'] == '江苏神通'
    assert review['completed'] == 4
    assert review['by_type']['BUY']['completed'] == 2
    assert review['by_type']['SELL']['completed'] == 2
    assert len(review['recent_resolved']) == 4
    assert review['recent_resolved'][0]['time'] == '14:42:00'
    assert review['stage'] in ('normal', 'watch')


def test_risk_guard_pause_triggered_by_drawdown(load_app):
    app_module = load_app()
    today = datetime.datetime.now().strftime('%Y-%m-%d')
    with app_module.state_lock:
        app_module.success_rates['risk_guard_enabled'] = True
        app_module.success_rates['risk_max_consecutive_fail'] = 99
        app_module.success_rates['risk_stock_max_consecutive_fail'] = 99
        app_module.success_rates['risk_daily_profit_floor'] = -99
        app_module.success_rates['risk_max_drawdown_pct'] = 1.0
        app_module.success_rates['risk_pause_minutes'] = 1
    app_module.reset_risk_state_for_day(today)

    app_module.update_risk_state_on_resolution({'id': 'a', 'code': 'sh600079', 'time': '10:00:00', 'profit_pct': 1.2}, 'success')
    app_module.update_risk_state_on_resolution({'id': 'b', 'code': 'sh600079', 'time': '10:05:00', 'profit_pct': -2.5}, 'fail')

    paused, _, reason = app_module.is_risk_paused()
    assert paused is True
    assert reason == 'daily_drawdown_limit_breached'


def test_periodic_report_endpoint(load_app):
    app_module = load_app()
    conn = app_module.get_db()
    conn.execute(
        '''
        INSERT INTO signals (id, date, time, seq_no, code, name, type, level, price, desc, status, profit_pct, gross_profit_pct)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''',
        (
            'sig_periodic_demo', '2026-03-03', '10:00:00', 1, 'sh600079', '测试股票',
            'BUY', 1, 10.0, 'demo', 'success', 1.25, 1.30
        )
    )
    conn.commit()
    conn.close()

    client = app_module.app.test_client()
    resp = client.get('/api/reports/periodic?weeks=2&months=2')
    payload = resp.get_json()

    assert resp.status_code == 200
    assert payload.get('success') is True
    report = payload.get('report') or {}
    assert len(report.get('weekly_items') or []) == 2
    assert len(report.get('monthly_items') or []) == 2


def test_management_route_group_still_serves_core_endpoints(load_app):
    app_module = load_app()
    client = app_module.app.test_client()

    config_get_resp = client.get('/api/config')
    assert config_get_resp.status_code == 200
    config_get_payload = config_get_resp.get_json()
    assert config_get_payload.get('success') is True
    assert isinstance(config_get_payload.get('strategy'), dict)

    paper_resp = client.get('/api/paper/account')
    assert paper_resp.status_code == 200
    assert paper_resp.get_json().get('success') is True

    snapshots_resp = client.get('/api/config/snapshots?limit=5')
    assert snapshots_resp.status_code == 200
    snapshots_payload = snapshots_resp.get_json()
    assert snapshots_payload.get('success') is True
    assert isinstance(snapshots_payload.get('items'), list)

    history_resp = client.get('/api/history?days=1')
    assert history_resp.status_code == 200
    history_payload = history_resp.get_json()
    assert history_payload.get('success') is True
    assert 'signals' in history_payload
    assert 'daily_stats' in history_payload

    history_bad_days_resp = client.get('/api/history?days=not-a-number')
    assert history_bad_days_resp.status_code == 200
    history_bad_days_payload = history_bad_days_resp.get_json()
    assert history_bad_days_payload.get('success') is True
    assert 'signals' in history_bad_days_payload


def test_report_route_group_still_serves_debug_and_daily_endpoints(load_app):
    app_module = load_app()
    client = app_module.app.test_client()

    debug_resp = client.get('/api/debug/logs?limit=20')
    assert debug_resp.status_code == 200
    debug_payload = debug_resp.get_json()
    assert isinstance(debug_payload.get('entries'), list)

    daily_resp = client.get('/api/reports/daily?generate=0')
    assert daily_resp.status_code == 200
    daily_payload = daily_resp.get_json()
    assert 'report' in daily_payload
    assert 'json_path' in daily_payload


def test_remove_focus_stock_is_blocked(load_app):
    app_module = load_app()
    with app_module.state_lock:
        app_module.active_stocks.clear()
        app_module.active_stocks[app_module.FOCUS_STOCK_CODE] = app_module.FOCUS_STOCK_NAME

    client = app_module.app.test_client()
    resp = client.delete(f'/api/stocks/{app_module.FOCUS_STOCK_CODE}')
    payload = resp.get_json()

    assert resp.status_code == 400
    assert payload.get('success') is False
    assert '固定首票' in (payload.get('msg') or '')


def test_remove_stock_keeps_history_and_force_closes_pending(load_app):
    app_module = load_app()
    today = datetime.datetime.now().strftime('%Y-%m-%d')

    with app_module.state_lock:
        app_module.active_stocks.clear()
        app_module.active_stocks[app_module.FOCUS_STOCK_CODE] = app_module.FOCUS_STOCK_NAME
        app_module.active_stocks['sh600079'] = '测试股票'
        app_module.market_data.clear()
        app_module.market_data['sh600079'] = [
            {'time': '10:30:00', 'price': 10.30, 'vwap': 10.20, 'ts': 1.0}
        ]
        app_module.signals_history.clear()
        app_module.pending_signals.clear()
        app_module.success_rates['trade_cost_buffer'] = 0.0
        app_module.success_rates['stocks'] = {}

    pending_sig = {
        'id': 'rm_pending_1', 'date': today, 'time': '10:05:00', 'seq_no': 2,
        'code': 'sh600079', 'name': '测试股票', 'type': 'BUY', 'level': 1,
        'price': 10.0, 'desc': 'pending-remove', 'status': 'pending'
    }
    resolved_sig = {
        'id': 'rm_done_1', 'date': today, 'time': '09:55:00', 'seq_no': 1,
        'code': 'sh600079', 'name': '测试股票', 'type': 'BUY', 'level': 1,
        'price': 10.0, 'desc': 'done-keep', 'status': 'success',
        'profit_pct': 1.0, 'gross_profit_pct': 1.1, 'resolved_price': 10.1
    }

    app_module.db_save_signal(pending_sig)
    conn = app_module.get_db()
    conn.execute(
        '''
        INSERT INTO signals (id, date, time, seq_no, code, name, type, level, price, desc, status, resolved_price, gross_profit_pct, profit_pct, resolve_msg)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''',
        (
            resolved_sig['id'], resolved_sig['date'], resolved_sig['time'], resolved_sig['seq_no'],
            resolved_sig['code'], resolved_sig['name'], resolved_sig['type'], resolved_sig['level'],
            resolved_sig['price'], resolved_sig['desc'], resolved_sig['status'], resolved_sig['resolved_price'],
            resolved_sig['gross_profit_pct'], resolved_sig['profit_pct'], 'manual-success'
        )
    )
    conn.commit()
    conn.close()

    with app_module.state_lock:
        app_module.signals_history[:] = [dict(pending_sig), dict(resolved_sig)]
        app_module.pending_signals[:] = [app_module.signals_history[0]]

    ok, msg = app_module.apply_remove_stock('sh600079', persist=False)

    assert ok is True
    assert msg == '测试股票'
    with app_module.state_lock:
        assert 'sh600079' not in app_module.active_stocks
        assert not app_module.pending_signals
        assert {item['id'] for item in app_module.signals_history} == {'rm_pending_1', 'rm_done_1'}
        resolved_pending = next(item for item in app_module.signals_history if item['id'] == 'rm_pending_1')
        assert resolved_pending['status'] == 'success'
        assert '移除自选时平仓' in (resolved_pending.get('resolve_msg') or '')

    conn = app_module.get_db()
    rows = conn.execute(
        "SELECT id, status, resolve_msg FROM signals WHERE code='sh600079' ORDER BY seq_no"
    ).fetchall()
    conn.close()
    assert len(rows) == 2
    assert {row['id'] for row in rows} == {'rm_pending_1', 'rm_done_1'}
    pending_row = next(row for row in rows if row['id'] == 'rm_pending_1')
    assert pending_row['status'] == 'success'
    assert '移除自选时平仓' in (pending_row['resolve_msg'] or '')


def test_history_endpoint_includes_execution_summary_and_paper_state(load_app):
    app_module = load_app()
    today = datetime.datetime.now().strftime('%Y-%m-%d')
    conn = app_module.get_db()
    conn.execute(
        '''
        INSERT INTO signals (id, date, time, seq_no, code, name, type, level, price, desc, status, profit_pct, gross_profit_pct)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''',
        ('hist_exec_1', today, '10:00:00', 1, 'sh600079', '测试股票', 'BUY', 1, 10.0, 'exec-win', 'success', 0.8, 0.9)
    )
    conn.execute(
        '''
        INSERT INTO signals (id, date, time, seq_no, code, name, type, level, price, desc, status, profit_pct, gross_profit_pct)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''',
        ('hist_exec_2', today, '10:15:00', 2, 'sh600079', '测试股票', 'SELL', 1, 10.0, 'exec-lose', 'fail', -0.4, -0.3)
    )
    conn.execute(
        '''
        INSERT INTO paper_orders (order_id, signal_id, date, time, code, name, side, qty, price, amount, fee, status, reason)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''',
        ('po_hist_1', 'hist_exec_1', today, '10:00:01', 'sh600079', '测试股票', 'BUY', 100, 10.0, 1000.0, 1.0, 'filled', 't_buy')
    )
    conn.execute(
        '''
        INSERT INTO paper_orders (order_id, signal_id, date, time, code, name, side, qty, price, amount, fee, status, reason)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''',
        ('po_hist_2', 'hist_exec_2', today, '10:15:01', 'sh600079', '测试股票', 'SELL', 0, 10.0, 0.0, 0.0, 'rejected', 'no_available_qty')
    )
    conn.commit()
    conn.close()

    client = app_module.app.test_client()
    resp = client.get('/api/history?days=7&code=sh600079')
    payload = resp.get_json()

    assert resp.status_code == 200
    assert payload.get('success') is True
    assert payload.get('execution', {}).get('signals_with_paper') == 2
    assert payload.get('execution', {}).get('signals_executed') == 1
    assert payload.get('execution', {}).get('signals_not_executed') == 1
    assert payload.get('execution', {}).get('totals', {}).get('total') == 1
    assert payload.get('execution', {}).get('totals', {}).get('success') == 1
    paper_statuses = {item['id']: ((item.get('paper') or {}).get('status')) for item in payload.get('signals') or []}
    assert paper_statuses['hist_exec_1'] == 'filled'
    assert paper_statuses['hist_exec_2'] == 'rejected'


def test_generate_daily_report_includes_execution_summary(load_app):
    app_module = load_app()
    today = datetime.datetime.now().strftime('%Y-%m-%d')
    conn = app_module.get_db()
    conn.execute(
        '''
        INSERT INTO signals (id, date, time, seq_no, code, name, type, level, price, desc, status, profit_pct, gross_profit_pct)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''',
        ('report_exec_1', today, '10:20:00', 1, 'sh600079', '测试股票', 'BUY', 1, 10.0, 'report-exec', 'success', 1.2, 1.3)
    )
    conn.execute(
        '''
        INSERT INTO paper_orders (order_id, signal_id, date, time, code, name, side, qty, price, amount, fee, status, reason)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''',
        ('po_report_1', 'report_exec_1', today, '10:20:01', 'sh600079', '测试股票', 'BUY', 100, 10.0, 1000.0, 1.0, 'filled', 't_buy')
    )
    conn.commit()
    conn.close()

    report, _ = app_module.generate_daily_report(today, trigger='manual_test')

    assert report['execution']['signals_with_paper'] == 1
    assert report['execution']['signals_executed'] == 1
    assert report['execution']['totals']['total'] == 1
    assert report['execution']['totals']['success'] == 1


def test_history_endpoint_supports_code_and_status_filters(load_app):
    app_module = load_app()
    today = datetime.datetime.now().strftime('%Y-%m-%d')
    conn = app_module.get_db()
    conn.execute(
        '''
        INSERT INTO signals (id, date, time, seq_no, code, name, type, level, price, desc, status, profit_pct, gross_profit_pct)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''',
        (
            'sig_filter_demo', today, '10:05:00', 1, 'sh600079', '测试股票',
            'BUY', 1, 10.0, 'filter-demo', 'success', 0.8, 0.9
        )
    )
    conn.commit()
    conn.close()

    client = app_module.app.test_client()

    filtered_resp = client.get('/api/history?days=7&code=sh600079&status=success')
    assert filtered_resp.status_code == 200
    filtered_payload = filtered_resp.get_json()
    assert filtered_payload.get('success') is True
    assert filtered_payload.get('query', {}).get('code') == 'sh600079'
    assert filtered_payload.get('query', {}).get('status') == 'success'
    assert len(filtered_payload.get('signals') or []) >= 1
    assert all((item.get('code') or '').lower() == 'sh600079' for item in filtered_payload.get('signals') or [])
    assert all((item.get('status') or '').lower() == 'success' for item in filtered_payload.get('signals') or [])

    invalid_status_resp = client.get('/api/history?days=7&status=weird')
    assert invalid_status_resp.status_code == 400
    invalid_status_payload = invalid_status_resp.get_json()
    assert invalid_status_payload.get('success') is False
    assert 'invalid status' in (invalid_status_payload.get('msg') or '')

    invalid_date_resp = client.get('/api/history?date=20260303')
    assert invalid_date_resp.status_code == 400
    invalid_date_payload = invalid_date_resp.get_json()
    assert invalid_date_payload.get('success') is False
    assert 'invalid date' in (invalid_date_payload.get('msg') or '')


def test_notify_test_endpoint_dispatches_via_hub(load_app):
    app_module = load_app()
    calls = []

    def fake_send_test(title='', body=''):
        calls.append({'title': title, 'body': body})
        return True, 'queued'

    app_module.notification_hub.send_test = fake_send_test
    client = app_module.app.test_client()

    resp = client.post('/api/notify/test', json={'title': '连通性测试', 'body': 'ok'})

    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload['success'] is True
    assert calls == [{'title': '连通性测试', 'body': 'ok'}]


def test_edge_diagnostics_endpoint_returns_focus_patch(load_app):
    app_module = load_app()
    conn = app_module.get_db()
    rows = [
        ('a1', '2026-03-07', '09:35:00', 1, 'sz002438', '江苏神通', 'BUY', 1, 10.0, 'd', 'fail', -0.8),
        ('a2', '2026-03-07', '09:48:00', 2, 'sz002438', '江苏神通', 'BUY', 1, 10.0, 'd', 'fail', -0.5),
        ('a3', '2026-03-07', '10:12:00', 3, 'sz002438', '江苏神通', 'BUY', 1, 10.0, 'd', 'success', 0.6),
        ('a4', '2026-03-07', '13:08:00', 4, 'sz002438', '江苏神通', 'BUY', 1, 10.0, 'd', 'fail', -0.4),
        ('a5', '2026-03-07', '13:42:00', 5, 'sz002438', '江苏神通', 'SELL', 1, 10.0, 'd', 'success', 0.7),
        ('a6', '2026-03-07', '14:36:00', 6, 'sz002438', '江苏神通', 'SELL', 1, 10.0, 'd', 'success', 0.5),
    ]
    conn.executemany(
        """
        INSERT INTO signals (id, date, time, seq_no, code, name, type, level, price, desc, status, profit_pct)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        rows
    )
    conn.commit()
    conn.close()

    client = app_module.app.test_client()
    resp = client.get('/api/analytics/edge-diagnostics?days=10&focus=sz002438&date=2026-03-07')

    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload['success'] is True
    diagnostics = payload['diagnostics']
    assert diagnostics['focus']['code'] == 'sz002438'
    assert diagnostics['focus_strategy']['profile_name'] == 'jsst_intraday_t_v1'
    patch = diagnostics['proposed_patch']['stock_strategies']['sz002438']
    assert patch['buy_min_score'] > 0.6
    assert patch['signal_profile']['signal_threshold'] >= 0.6


def test_tuning_apply_accepts_edge_diagnostics_patch(load_app):
    app_module = load_app()
    conn = app_module.get_db()
    rows = [
        ('b1', '2026-03-07', '09:35:00', 1, 'sz002438', '江苏神通', 'BUY', 1, 10.0, 'd', 'fail', -0.8),
        ('b2', '2026-03-07', '09:48:00', 2, 'sz002438', '江苏神通', 'BUY', 1, 10.0, 'd', 'fail', -0.5),
        ('b3', '2026-03-07', '10:12:00', 3, 'sz002438', '江苏神通', 'BUY', 1, 10.0, 'd', 'success', 0.6),
        ('b4', '2026-03-07', '13:08:00', 4, 'sz002438', '江苏神通', 'BUY', 1, 10.0, 'd', 'fail', -0.4),
        ('b5', '2026-03-07', '13:42:00', 5, 'sz002438', '江苏神通', 'SELL', 1, 10.0, 'd', 'success', 0.7),
        ('b6', '2026-03-07', '14:36:00', 6, 'sz002438', '江苏神通', 'SELL', 1, 10.0, 'd', 'success', 0.5),
    ]
    conn.executemany(
        """
        INSERT INTO signals (id, date, time, seq_no, code, name, type, level, price, desc, status, profit_pct)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        rows
    )
    conn.commit()
    conn.close()

    client = app_module.app.test_client()
    diag_resp = client.get('/api/analytics/edge-diagnostics?days=10&focus=sz002438&date=2026-03-07')
    assert diag_resp.status_code == 200
    diagnostics = diag_resp.get_json()['diagnostics']
    patch = diagnostics['proposed_patch']

    apply_resp = client.post(
        '/api/tuning/apply',
        json={
            'date': '2026-03-07',
            'patch': patch,
            'note': 'edge diagnostics apply'
        }
    )

    assert apply_resp.status_code == 200
    payload = apply_resp.get_json()
    assert payload['success'] is True
    assert payload['snapshot_id'] is not None
    applied_stock = payload['applied']['stock_strategies']['sz002438']
    patch_stock = patch['stock_strategies']['sz002438']
    assert applied_stock['buy_min_score'] == patch_stock['buy_min_score']
    assert applied_stock['signal_profile']['signal_threshold'] == patch_stock['signal_profile']['signal_threshold']

    strategy_after = payload['strategy_after']['stock_strategies']['sz002438']
    assert strategy_after['buy_min_score'] == patch_stock['buy_min_score']
    assert strategy_after['signal_profile']['signal_threshold'] == patch_stock['signal_profile']['signal_threshold']


def test_auto_focus_tuning_applies_once_per_date(load_app):
    app_module = load_app()
    conn = app_module.get_db()
    rows = [
        ('c1', '2026-03-07', '09:35:00', 1, 'sz002438', '江苏神通', 'BUY', 1, 10.0, 'd', 'fail', -0.8),
        ('c2', '2026-03-07', '09:48:00', 2, 'sz002438', '江苏神通', 'BUY', 1, 10.0, 'd', 'fail', -0.5),
        ('c3', '2026-03-07', '10:12:00', 3, 'sz002438', '江苏神通', 'BUY', 1, 10.0, 'd', 'success', 0.6),
        ('c4', '2026-03-07', '13:08:00', 4, 'sz002438', '江苏神通', 'BUY', 1, 10.0, 'd', 'fail', -0.4),
        ('c5', '2026-03-07', '13:42:00', 5, 'sz002438', '江苏神通', 'SELL', 1, 10.0, 'd', 'success', 0.7),
        ('c6', '2026-03-07', '14:36:00', 6, 'sz002438', '江苏神通', 'SELL', 1, 10.0, 'd', 'success', 0.5),
    ]
    conn.executemany(
        """
        INSERT INTO signals (id, date, time, seq_no, code, name, type, level, price, desc, status, profit_pct)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        rows
    )
    conn.commit()
    conn.close()

    app_module.ensure_stock_strategy('sz002438')
    result = app_module.maybe_auto_apply_focus_tuning('2026-03-07')

    assert result['applied'] is True
    assert result['snapshot_id'] is not None
    assert result['run_id'] is not None
    assert os.path.exists(result['saved_path'])

    run = app_module.get_tuning_run('2026-03-07', 'sz002438')
    assert run is not None

    patch_stock = result['applied_patch']['stock_strategies']['sz002438']
    strategy_after = app_module.get_strategy_snapshot()['stock_strategies']['sz002438']
    assert strategy_after['buy_min_score'] == patch_stock['buy_min_score']
    assert strategy_after['signal_profile']['signal_threshold'] == patch_stock['signal_profile']['signal_threshold']

    again = app_module.maybe_auto_apply_focus_tuning('2026-03-07')
    assert again['applied'] is False
    assert again['reason'] == 'already_applied'


def test_auto_focus_tuning_prefers_target_date_weak_side_and_slot(load_app):
    app_module = load_app()
    conn = app_module.get_db()
    rows = [
        ('e1', '2026-03-06', '09:35:00', 1, 'sz002438', '江苏神通', 'BUY', 1, 10.0, 'd', 'success', 0.8),
        ('e2', '2026-03-06', '10:05:00', 2, 'sz002438', '江苏神通', 'BUY', 1, 10.0, 'd', 'success', 0.5),
        ('e3', '2026-03-06', '13:08:00', 3, 'sz002438', '江苏神通', 'BUY', 1, 10.0, 'd', 'success', 0.6),
        ('e4', '2026-03-06', '13:42:00', 4, 'sz002438', '江苏神通', 'BUY', 1, 10.0, 'd', 'success', 0.4),
        ('e5', '2026-03-07', '10:18:00', 5, 'sz002438', '江苏神通', 'BUY', 1, 10.0, 'd', 'success', 0.3),
        ('e6', '2026-03-07', '14:35:00', 6, 'sz002438', '江苏神通', 'SELL', 1, 10.0, 'd', 'fail', -0.7),
        ('e7', '2026-03-07', '14:42:00', 7, 'sz002438', '江苏神通', 'SELL', 1, 10.0, 'd', 'fail', -0.4),
    ]
    conn.executemany(
        """
        INSERT INTO signals (id, date, time, seq_no, code, name, type, level, price, desc, status, profit_pct)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        rows
    )
    conn.commit()
    conn.close()

    app_module.ensure_stock_strategy('sz002438')
    before_templates = app_module.get_time_slot_templates_for_code('sz002438')
    before_base = app_module.derive_baseline_strategy_from_templates(before_templates)
    result = app_module.maybe_auto_apply_focus_tuning('2026-03-07')

    assert result['applied'] is True
    patch_stock = result['applied_patch']['stock_strategies']['sz002438']
    assert 'sell_min_score' in patch_stock
    assert 'buy_min_score' not in patch_stock
    assert round(patch_stock['sell_min_score'] - before_base['sell_min_score'], 4) == 0.01
    assert patch_stock['time_slot_templates']['close']['sell_min_score'] == round(before_templates['close']['sell_min_score'] + 0.01, 4)
    assert result['auto_meta']['selected_side'] == 'SELL'
    assert result['auto_meta']['selected_slot'] == 'close'
    assert any('SELL 偏弱' in line for line in result['patch_summary'])


def test_auto_focus_tuning_skips_without_focus_samples_on_target_date(load_app):
    app_module = load_app()
    conn = app_module.get_db()
    rows = [
        ('d1', '2026-03-06', '09:35:00', 1, 'sz002438', '江苏神通', 'BUY', 1, 10.0, 'd', 'fail', -0.8),
        ('d2', '2026-03-06', '09:48:00', 2, 'sz002438', '江苏神通', 'BUY', 1, 10.0, 'd', 'fail', -0.5),
        ('d3', '2026-03-06', '10:12:00', 3, 'sz002438', '江苏神通', 'BUY', 1, 10.0, 'd', 'success', 0.6),
        ('d4', '2026-03-06', '13:08:00', 4, 'sz002438', '江苏神通', 'BUY', 1, 10.0, 'd', 'fail', -0.4),
        ('d5', '2026-03-06', '13:42:00', 5, 'sz002438', '江苏神通', 'SELL', 1, 10.0, 'd', 'success', 0.7),
        ('d6', '2026-03-06', '14:36:00', 6, 'sz002438', '江苏神通', 'SELL', 1, 10.0, 'd', 'success', 0.5),
    ]
    conn.executemany(
        """
        INSERT INTO signals (id, date, time, seq_no, code, name, type, level, price, desc, status, profit_pct)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        rows
    )
    conn.commit()
    conn.close()

    app_module.ensure_stock_strategy('sz002438')
    before = app_module.get_strategy_snapshot()['stock_strategies']['sz002438']
    result = app_module.maybe_auto_apply_focus_tuning('2026-03-07')

    assert result['applied'] is False
    assert result['reason'] == 'no_focus_samples_on_target_date'
    assert app_module.get_tuning_run('2026-03-07', 'sz002438') is None

    after = app_module.get_strategy_snapshot()['stock_strategies']['sz002438']
    assert after == before
