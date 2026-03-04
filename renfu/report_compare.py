def compare_reports(current_report, baseline_report):
    def diff(a, b):
        return round(float(a) - float(b), 4)

    cur_tot = current_report.get('totals', {})
    base_tot = baseline_report.get('totals', {})
    totals_diff = {k: diff(cur_tot.get(k, 0), base_tot.get(k, 0)) for k in ('total', 'success', 'fail', 'pending', 'completed', 'win_rate')}

    type_diff = {}
    cur_type = current_report.get('by_type', {})
    base_type = baseline_report.get('by_type', {})
    for sig_type in set(list(cur_type.keys()) + list(base_type.keys())):
        cur_item = cur_type.get(sig_type, {})
        base_item = base_type.get(sig_type, {})
        type_diff[sig_type] = {
            k: diff(cur_item.get(k, 0), base_item.get(k, 0))
            for k in ('total', 'success', 'fail', 'pending', 'win_rate', 'avg_profit_pct')
        }

    cur_rej = current_report.get('debug_summary', {}).get('reject_reasons', {})
    base_rej = baseline_report.get('debug_summary', {}).get('reject_reasons', {})
    reason_diff = {}
    for key in set(list(cur_rej.keys()) + list(base_rej.keys())):
        reason_diff[key] = int(cur_rej.get(key, 0)) - int(base_rej.get(key, 0))
    reason_diff = dict(sorted(reason_diff.items(), key=lambda x: abs(x[1]), reverse=True)[:15])

    return {
        'totals_diff': totals_diff,
        'by_type_diff': type_diff,
        'reject_reason_diff': reason_diff
    }
