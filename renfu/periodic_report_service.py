import collections
import datetime


def compute_max_drawdown(curve):
    peak = 0.0
    max_dd = 0.0
    for point in list(curve or []):
        value = float(point or 0.0)
        peak = max(peak, value)
        max_dd = max(max_dd, peak - value)
    return max_dd


def summarize_period_performance(get_signal_rows, date_from, date_to, label=''):
    rows = get_signal_rows(date_from=date_from, date_to=date_to)
    total = len(rows)
    success = 0
    fail = 0
    pending = 0
    curve = []
    cum_profit = 0.0
    daily_profit_map = collections.defaultdict(float)
    by_type = collections.defaultdict(lambda: {'total': 0, 'success': 0, 'fail': 0, 'profit_sum': 0.0, 'profit_n': 0})

    for row in rows:
        sig_type = str(row.get('type') or 'UNKNOWN')
        by_type[sig_type]['total'] += 1
        status = str(row.get('status') or '')
        if status == 'success':
            success += 1
            by_type[sig_type]['success'] += 1
            profit = float(row.get('profit_pct') or 0.0)
            by_type[sig_type]['profit_sum'] += profit
            by_type[sig_type]['profit_n'] += 1
            cum_profit += profit
            curve.append(cum_profit)
            daily_profit_map[str(row.get('date') or '')] += profit
        elif status == 'fail':
            fail += 1
            by_type[sig_type]['fail'] += 1
            profit = float(row.get('profit_pct') or 0.0)
            by_type[sig_type]['profit_sum'] += profit
            by_type[sig_type]['profit_n'] += 1
            cum_profit += profit
            curve.append(cum_profit)
            daily_profit_map[str(row.get('date') or '')] += profit
        else:
            pending += 1

    completed = success + fail
    by_type_out = {}
    for sig_type, item in by_type.items():
        item_completed = item['success'] + item['fail']
        by_type_out[sig_type] = {
            'total': item['total'],
            'success': item['success'],
            'fail': item['fail'],
            'win_rate': round(item['success'] * 100.0 / item_completed, 2) if item_completed else 0.0,
            'avg_profit_pct': round(item['profit_sum'] / item['profit_n'], 4) if item['profit_n'] else 0.0
        }

    daily_curve = []
    running = 0.0
    for day in sorted(daily_profit_map.keys()):
        running += float(daily_profit_map[day])
        daily_curve.append({'date': day, 'cum_profit_pct': round(running, 4), 'day_profit_pct': round(float(daily_profit_map[day]), 4)})

    return {
        'label': label,
        'date_from': date_from,
        'date_to': date_to,
        'total': total,
        'completed': completed,
        'success': success,
        'fail': fail,
        'pending': pending,
        'win_rate': round(success * 100.0 / completed, 2) if completed else 0.0,
        'net_profit_pct': round(cum_profit, 4),
        'avg_profit_pct': round(cum_profit / completed, 4) if completed else 0.0,
        'max_drawdown_pct': round(compute_max_drawdown(curve), 4),
        'by_type': by_type_out,
        'daily_curve': daily_curve
    }


def shift_month(year, month, delta):
    year_int = int(year)
    month_int = int(month)
    total_month = (year_int * 12 + (month_int - 1)) + int(delta)
    new_year = total_month // 12
    new_month = (total_month % 12) + 1
    return new_year, new_month


def build_periodic_report(get_signal_rows, weeks=8, months=6):
    today = datetime.date.today()
    weeks = max(1, min(int(weeks), 52))
    months = max(1, min(int(months), 24))

    weekly_items = []
    week_anchor = today - datetime.timedelta(days=today.weekday())
    for idx in range(weeks):
        start = week_anchor - datetime.timedelta(days=idx * 7)
        end = start + datetime.timedelta(days=6)
        label = f"{start.isoformat()}~{end.isoformat()}"
        weekly_items.append(
            summarize_period_performance(get_signal_rows, start.strftime('%Y-%m-%d'), end.strftime('%Y-%m-%d'), label=label)
        )
    weekly_items.sort(key=lambda x: x.get('date_from', ''))

    monthly_items = []
    year, month = today.year, today.month
    for idx in range(months):
        yy, mm = shift_month(year, month, -idx)
        start = datetime.date(yy, mm, 1)
        next_year, next_month = shift_month(yy, mm, 1)
        end = datetime.date(next_year, next_month, 1) - datetime.timedelta(days=1)
        label = f"{yy:04d}-{mm:02d}"
        monthly_items.append(
            summarize_period_performance(get_signal_rows, start.strftime('%Y-%m-%d'), end.strftime('%Y-%m-%d'), label=label)
        )
    monthly_items.sort(key=lambda x: x.get('date_from', ''))

    week_summary = weekly_items[-1] if weekly_items else {}
    month_summary = monthly_items[-1] if monthly_items else {}
    return {
        'generated_at': datetime.datetime.now().isoformat(timespec='seconds'),
        'week_summary': week_summary,
        'month_summary': month_summary,
        'weekly_items': weekly_items,
        'monthly_items': monthly_items
    }
