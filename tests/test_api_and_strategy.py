import datetime


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
    assert 'signals' in history_payload
    assert 'daily_stats' in history_payload

    history_bad_days_resp = client.get('/api/history?days=not-a-number')
    assert history_bad_days_resp.status_code == 200
    history_bad_days_payload = history_bad_days_resp.get_json()
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
