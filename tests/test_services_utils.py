import sqlite3

from renfu.date_utils import is_valid_iso_date, normalize_date_str
from renfu.debug_summary import summarize_debug_entries
from renfu.history_service import query_signal_history
from renfu.periodic_report_service import build_periodic_report
from renfu.report_compare import compare_reports
from renfu.request_args import parse_int_value, parse_since_ts_arg


def test_parse_int_value_fallback_and_clamp():
    assert parse_int_value('12', 5) == 12
    assert parse_int_value('bad', 5) == 5
    assert parse_int_value('-9', 5, min_value=1) == 1
    assert parse_int_value('99', 5, max_value=10) == 10


def test_parse_since_ts_arg_accepts_seconds_and_milliseconds():
    assert parse_since_ts_arg('1700000000') == 1700000000.0
    assert parse_since_ts_arg('1700000000000') == 1700000000.0
    assert parse_since_ts_arg('bad') is None
    assert parse_since_ts_arg('-3') is None


def test_date_utils_normalize_and_validate():
    assert normalize_date_str('2026-03-04') == '2026-03-04'
    assert normalize_date_str('20260304') is None
    assert is_valid_iso_date('2026-03-04') is True
    assert is_valid_iso_date('2026-02-30') is False


def test_summarize_debug_entries_groups_key_counters():
    entries = [
        {'event': 'signal_accepted', 'code': 'sh600079', 'signal_type': 'BUY'},
        {'event': 'signal_rejected', 'code': 'sh600079', 'signal_type': 'BUY', 'reasons': ['buy_min_score']},
        {'event': 'signal_resolved', 'code': 'sh600079', 'signal_type': 'BUY', 'status': 'success'},
    ]
    summary = summarize_debug_entries(entries)
    assert summary['sample_size'] == 3
    assert summary['event_counts'].get('signal_accepted') == 1
    assert summary['reject_reasons'].get('buy_min_score') == 1
    assert summary['by_code']['sh600079']['resolved_success'] == 1


def test_compare_reports_returns_expected_diffs():
    current = {
        'totals': {'total': 10, 'success': 6, 'fail': 2, 'pending': 2, 'completed': 8, 'win_rate': 75.0},
        'by_type': {'BUY': {'total': 8, 'success': 5, 'fail': 1, 'pending': 2, 'win_rate': 83.33, 'avg_profit_pct': 1.2}},
        'debug_summary': {'reject_reasons': {'buy_min_score': 5}},
    }
    baseline = {
        'totals': {'total': 8, 'success': 4, 'fail': 2, 'pending': 2, 'completed': 6, 'win_rate': 66.67},
        'by_type': {'BUY': {'total': 6, 'success': 3, 'fail': 1, 'pending': 2, 'win_rate': 75.0, 'avg_profit_pct': 1.0}},
        'debug_summary': {'reject_reasons': {'buy_min_score': 2}},
    }
    out = compare_reports(current, baseline)
    assert out['totals_diff']['success'] == 2.0
    assert round(out['totals_diff']['win_rate'], 2) == 8.33
    assert out['by_type_diff']['BUY']['total'] == 2.0
    assert out['reject_reason_diff']['buy_min_score'] == 3


def test_query_signal_history_with_filters():
    conn = sqlite3.connect(':memory:')
    conn.row_factory = sqlite3.Row
    conn.execute(
        '''
        CREATE TABLE signals (
            id TEXT,
            date TEXT,
            time TEXT,
            created_at TEXT,
            code TEXT,
            status TEXT
        )
        '''
    )
    conn.execute(
        '''
        CREATE TABLE daily_stats (
            date TEXT,
            total INTEGER,
            success INTEGER,
            fail INTEGER,
            win_rate REAL
        )
        '''
    )
    conn.execute(
        "INSERT INTO signals (id, date, time, created_at, code, status) VALUES (?, ?, ?, ?, ?, ?)",
        ('a', '2026-03-03', '10:00:00', '2026-03-03 10:00:00', 'sh600079', 'success')
    )
    conn.execute(
        "INSERT INTO signals (id, date, time, created_at, code, status) VALUES (?, ?, ?, ?, ?, ?)",
        ('b', '2026-03-03', '10:01:00', '2026-03-03 10:01:00', 'sh688563', 'fail')
    )
    conn.execute(
        "INSERT INTO daily_stats (date, total, success, fail, win_rate) VALUES (?, ?, ?, ?, ?)",
        ('2026-03-03', 2, 1, 1, 50.0)
    )
    conn.commit()

    payload = query_signal_history(
        conn,
        date_q='2026-03-03',
        days_q=7,
        code_q='sh600079',
        status_q='success',
        limit_q=100
    )
    assert payload['success'] is True
    assert payload['query']['date'] == '2026-03-03'
    assert payload['query']['code'] == 'sh600079'
    assert payload['query']['status'] == 'success'
    assert len(payload['signals']) == 1
    assert payload['signals'][0]['code'] == 'sh600079'


def test_build_periodic_report_with_mock_rows():
    def fake_get_signal_rows(date_from=None, date_to=None):
        return [
            {'date': date_from, 'type': 'BUY', 'status': 'success', 'profit_pct': 1.2},
            {'date': date_from, 'type': 'BUY', 'status': 'fail', 'profit_pct': -0.4},
            {'date': date_from, 'type': 'SELL', 'status': 'pending', 'profit_pct': 0.0},
        ]

    report = build_periodic_report(fake_get_signal_rows, weeks=2, months=2)
    assert len(report.get('weekly_items') or []) == 2
    assert len(report.get('monthly_items') or []) == 2
    week_summary = report.get('week_summary') or {}
    assert week_summary.get('total') == 3
    assert week_summary.get('completed') == 2
