import datetime


VALID_SIGNAL_STATUS = {'pending', 'success', 'fail'}


def query_signal_history(
    conn,
    *,
    date_q=None,
    days_q=7,
    code_q='',
    status_q='',
    limit_q=500
):
    signal_sql = []
    signal_params = []

    if date_q:
        signal_sql.append('SELECT * FROM signals WHERE date=?')
        signal_params.append(date_q)
        stats = conn.execute('SELECT * FROM daily_stats WHERE date=?', (date_q,)).fetchone()
    else:
        since = (datetime.datetime.now() - datetime.timedelta(days=days_q)).strftime('%Y-%m-%d')
        signal_sql.append('SELECT * FROM signals WHERE date>=?')
        signal_params.append(since)
        stats = None

    if code_q:
        signal_sql.append('AND LOWER(code)=?')
        signal_params.append(code_q)
    if status_q:
        signal_sql.append('AND status=?')
        signal_params.append(status_q)

    if date_q:
        signal_sql.append('ORDER BY created_at DESC')
    else:
        signal_sql.append('ORDER BY date DESC, created_at DESC')
    signal_sql.append('LIMIT ?')
    signal_params.append(limit_q)

    signals = conn.execute(' '.join(signal_sql), tuple(signal_params)).fetchall()
    daily = conn.execute('SELECT * FROM daily_stats ORDER BY date DESC LIMIT ?', (days_q,)).fetchall()

    return {
        'success': True,
        'signals': [dict(r) for r in signals],
        'daily_stats': [dict(r) for r in daily],
        'date_stats': dict(stats) if stats else None,
        'query': {
            'date': date_q,
            'days': days_q,
            'code': code_q or None,
            'status': status_q or None,
            'limit': limit_q
        }
    }
