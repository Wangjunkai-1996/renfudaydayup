from renfu.edge_diagnostics import build_edge_diagnostics


def test_build_edge_diagnostics_focus_and_suggestions():
    rows = [
        {'date': '2026-03-07', 'time': '09:35:00', 'code': 'sz002438', 'name': '江苏神通', 'type': 'BUY', 'status': 'fail', 'profit_pct': -0.8},
        {'date': '2026-03-07', 'time': '09:48:00', 'code': 'sz002438', 'name': '江苏神通', 'type': 'BUY', 'status': 'fail', 'profit_pct': -0.5},
        {'date': '2026-03-07', 'time': '10:12:00', 'code': 'sz002438', 'name': '江苏神通', 'type': 'BUY', 'status': 'success', 'profit_pct': 0.6},
        {'date': '2026-03-07', 'time': '13:08:00', 'code': 'sz002438', 'name': '江苏神通', 'type': 'BUY', 'status': 'fail', 'profit_pct': -0.4},
        {'date': '2026-03-07', 'time': '13:42:00', 'code': 'sz002438', 'name': '江苏神通', 'type': 'SELL', 'status': 'success', 'profit_pct': 0.7},
        {'date': '2026-03-07', 'time': '14:36:00', 'code': 'sz002438', 'name': '江苏神通', 'type': 'SELL', 'status': 'success', 'profit_pct': 0.5},
        {'date': '2026-03-07', 'time': '10:05:00', 'code': 'sz300402', 'name': '宝色股份', 'type': 'BUY', 'status': 'success', 'profit_pct': 0.9},
    ]

    diagnostics = build_edge_diagnostics(rows, focus_code='sz002438', focus_name='江苏神通')

    assert diagnostics['summary']['stock_count'] == 2
    assert diagnostics['focus']['code'] == 'sz002438'
    assert diagnostics['focus']['completed'] == 6
    assert diagnostics['focus']['by_type']['BUY']['win_rate'] == 25.0
    assert diagnostics['focus']['worst_slot']['slot'] == 'open'
    assert any('BUY 胜率偏弱' in item['msg'] for item in diagnostics['suggestions'])


def test_build_edge_diagnostics_handles_no_focus_samples():
    diagnostics = build_edge_diagnostics([], focus_code='sz002438', focus_name='江苏神通')

    assert diagnostics['focus'] is None
    assert diagnostics['summary']['total'] == 0
    assert any('暂无真实成交样本' in item['msg'] for item in diagnostics['suggestions'])
