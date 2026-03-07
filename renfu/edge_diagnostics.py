import collections


SIGNAL_TYPES = ('BUY', 'SELL')
SLOT_ORDER = ('open', 'morning', 'afternoon_open', 'afternoon', 'close', 'off_hours')
SLOT_LABELS = {
    'open': '开盘段',
    'morning': '上午盘',
    'afternoon_open': '午后开盘',
    'afternoon': '午后盘',
    'close': '尾盘',
    'off_hours': '非交易时段'
}


def classify_time_slot(time_str=None):
    try:
        text = str(time_str or '').strip()
        if len(text) >= 5:
            hour = int(text[0:2])
            minute = int(text[3:5])
        else:
            return 'off_hours'
    except Exception:
        return 'off_hours'

    minute_of_day = hour * 60 + minute
    if 9 * 60 + 30 <= minute_of_day < 10 * 60:
        return 'open'
    if 10 * 60 <= minute_of_day <= 11 * 60 + 30:
        return 'morning'
    if 13 * 60 <= minute_of_day < 13 * 60 + 30:
        return 'afternoon_open'
    if 13 * 60 + 30 <= minute_of_day < 14 * 60 + 30:
        return 'afternoon'
    if 14 * 60 + 30 <= minute_of_day <= 15 * 60:
        return 'close'
    return 'off_hours'


def _new_bucket():
    return {
        'total': 0,
        'completed': 0,
        'success': 0,
        'fail': 0,
        'pending': 0,
        'profit_sum': 0.0,
        'profit_n': 0
    }


def _update_bucket(bucket, row):
    bucket['total'] += 1
    status = str(row.get('status') or '').lower()
    if status in ('success', 'fail'):
        bucket['completed'] += 1
        bucket[status] += 1
        bucket['profit_sum'] += float(row.get('profit_pct') or 0.0)
        bucket['profit_n'] += 1
    else:
        bucket['pending'] += 1


def _finalize_bucket(bucket):
    completed = int(bucket.get('completed', 0) or 0)
    success = int(bucket.get('success', 0) or 0)
    profit_n = int(bucket.get('profit_n', 0) or 0)
    return {
        'total': int(bucket.get('total', 0) or 0),
        'completed': completed,
        'success': success,
        'fail': int(bucket.get('fail', 0) or 0),
        'pending': int(bucket.get('pending', 0) or 0),
        'win_rate': round(success * 100.0 / completed, 2) if completed else 0.0,
        'avg_profit_pct': round(float(bucket.get('profit_sum', 0.0) or 0.0) / profit_n, 4) if profit_n else 0.0
    }


def _new_slot_state():
    return {
        'metrics': _new_bucket(),
        'by_type': collections.defaultdict(_new_bucket)
    }


def _new_stock_state():
    return {
        'name': '',
        'metrics': _new_bucket(),
        'by_type': collections.defaultdict(_new_bucket),
        'slots': collections.defaultdict(_new_slot_state)
    }


def _build_strengths_and_risks(stock_item):
    strengths = []
    risks = []
    buy = (stock_item.get('by_type') or {}).get('BUY', {})
    sell = (stock_item.get('by_type') or {}).get('SELL', {})
    worst_slot = stock_item.get('worst_slot') or {}

    if stock_item.get('completed', 0) >= 6 and stock_item.get('win_rate', 0.0) >= 60 and stock_item.get('avg_profit_pct', 0.0) > 0:
        strengths.append(f"整体净胜率较稳({stock_item.get('win_rate', 0.0):.1f}%)")
    if buy.get('completed', 0) >= 4 and buy.get('win_rate', 0.0) >= 60:
        strengths.append(f"BUY 方向较稳({buy.get('win_rate', 0.0):.1f}%)")
    if sell.get('completed', 0) >= 4 and sell.get('win_rate', 0.0) >= 60:
        strengths.append(f"SELL 方向较稳({sell.get('win_rate', 0.0):.1f}%)")

    if stock_item.get('completed', 0) >= 4 and stock_item.get('win_rate', 0.0) < 45:
        risks.append(f"整体净胜率偏低({stock_item.get('win_rate', 0.0):.1f}%)")
    if stock_item.get('completed', 0) >= 4 and stock_item.get('avg_profit_pct', 0.0) < 0:
        risks.append(f"已完成样本均笔收益为负({stock_item.get('avg_profit_pct', 0.0):+.3f}%)")
    if buy.get('completed', 0) >= 4 and buy.get('win_rate', 0.0) < 45:
        risks.append(f"BUY 胜率偏弱({buy.get('win_rate', 0.0):.1f}%)")
    if sell.get('completed', 0) >= 4 and sell.get('win_rate', 0.0) < 45:
        risks.append(f"SELL 胜率偏弱({sell.get('win_rate', 0.0):.1f}%)")
    if worst_slot.get('completed', 0) >= 3 and worst_slot.get('win_rate', 0.0) < 45:
        risks.append(f"{SLOT_LABELS.get(worst_slot.get('slot'), worst_slot.get('slot'))} 表现最弱({worst_slot.get('win_rate', 0.0):.1f}%)")

    return strengths[:3], risks[:4]


def build_edge_diagnostics(rows, focus_code='', focus_name=''):
    normalized_focus_code = str(focus_code or '').strip().lower()
    overall_bucket = _new_bucket()
    stock_map = collections.defaultdict(_new_stock_state)

    for raw_row in list(rows or []):
        row = dict(raw_row or {})
        code = str(row.get('code') or '').strip().lower()
        if not code:
            continue
        stock_state = stock_map[code]
        stock_state['name'] = str(row.get('name') or stock_state.get('name') or '').strip()
        signal_type = str(row.get('type') or '').strip().upper() or 'UNKNOWN'
        slot = classify_time_slot(row.get('time'))

        _update_bucket(overall_bucket, row)
        _update_bucket(stock_state['metrics'], row)
        _update_bucket(stock_state['by_type'][signal_type], row)
        _update_bucket(stock_state['slots'][slot]['metrics'], row)
        _update_bucket(stock_state['slots'][slot]['by_type'][signal_type], row)

    stock_items = []
    for code, stock_state in stock_map.items():
        stock_metrics = _finalize_bucket(stock_state['metrics'])
        by_type = {
            signal_type: _finalize_bucket(stock_state['by_type'].get(signal_type, _new_bucket()))
            for signal_type in SIGNAL_TYPES
        }
        slot_items = []
        for slot in SLOT_ORDER:
            slot_state = stock_state['slots'].get(slot)
            if not slot_state:
                continue
            slot_metrics = _finalize_bucket(slot_state['metrics'])
            slot_metrics['slot'] = slot
            slot_metrics['label'] = SLOT_LABELS.get(slot, slot)
            slot_metrics['by_type'] = {
                signal_type: _finalize_bucket(slot_state['by_type'].get(signal_type, _new_bucket()))
                for signal_type in SIGNAL_TYPES
            }
            slot_items.append(slot_metrics)

        ranked_slots = [item for item in slot_items if item.get('completed', 0) > 0]
        best_slot = None
        worst_slot = None
        if ranked_slots:
            best_slot = max(ranked_slots, key=lambda item: (item.get('win_rate', 0.0), item.get('avg_profit_pct', 0.0), item.get('completed', 0)))
            worst_slot = min(ranked_slots, key=lambda item: (item.get('win_rate', 0.0), item.get('avg_profit_pct', 0.0), -item.get('completed', 0)))

        stock_item = {
            'code': code,
            'name': stock_state.get('name') or (focus_name if code == normalized_focus_code else ''),
            **stock_metrics,
            'by_type': by_type,
            'slots': slot_items,
            'best_slot': dict(best_slot) if best_slot else None,
            'worst_slot': dict(worst_slot) if worst_slot else None
        }
        strengths, risks = _build_strengths_and_risks(stock_item)
        stock_item['strengths'] = strengths
        stock_item['risks'] = risks
        stock_items.append(stock_item)

    stock_items.sort(
        key=lambda item: (
            0 if item.get('code') == normalized_focus_code else 1,
            -int(item.get('completed', 0) or 0),
            -int(item.get('total', 0) or 0),
            item.get('code') or ''
        )
    )

    focus_item = None
    for item in stock_items:
        if item.get('code') == normalized_focus_code:
            focus_item = item
            break

    overall = _finalize_bucket(overall_bucket)
    overall['stock_count'] = len(stock_items)
    overall['focus_code'] = normalized_focus_code
    overall['focus_name'] = focus_item.get('name') if focus_item else focus_name

    suggestions = []
    if normalized_focus_code:
        display_name = (focus_item or {}).get('name') or focus_name or normalized_focus_code
        if not focus_item or focus_item.get('total', 0) <= 0:
            suggestions.append({'level': 'info', 'msg': f'{display_name} 暂无真实成交样本，先累计到 6 笔以上再做精细调参'})
        else:
            if focus_item.get('completed', 0) < 6:
                suggestions.append({'level': 'info', 'msg': f'{display_name} 当前已完成样本只有 {focus_item.get("completed", 0)} 笔，先观察稳定性，不急着频繁改参数'})
            if focus_item.get('avg_profit_pct', 0.0) < 0 and focus_item.get('completed', 0) >= 4:
                suggestions.append({'level': 'warn', 'msg': f'{display_name} 已完成样本均笔收益为负，先提高入场质量，优先保胜率'})
            buy = (focus_item.get('by_type') or {}).get('BUY', {}) if focus_item else {}
            sell = (focus_item.get('by_type') or {}).get('SELL', {}) if focus_item else {}
            if buy.get('completed', 0) >= 4 and buy.get('win_rate', 0.0) < 45:
                suggestions.append({'level': 'warn', 'msg': f'{display_name} 的 BUY 胜率偏弱({buy.get("win_rate", 0.0):.1f}%)，建议抬高 BUY 门槛'})
            if sell.get('completed', 0) >= 4 and sell.get('win_rate', 0.0) < 45:
                suggestions.append({'level': 'warn', 'msg': f'{display_name} 的 SELL 胜率偏弱({sell.get("win_rate", 0.0):.1f}%)，建议抬高 SELL 门槛'})
            worst_slot = focus_item.get('worst_slot') if focus_item else None
            if worst_slot and worst_slot.get('completed', 0) >= 3 and worst_slot.get('win_rate', 0.0) < 45:
                suggestions.append({'level': 'warn', 'msg': f'{display_name} 在 {worst_slot.get("label")} 最弱({worst_slot.get("win_rate", 0.0):.1f}%)，建议单独收紧该时段'})
            if not suggestions:
                suggestions.append({'level': 'info', 'msg': f'{display_name} 暂无明显结构性弱点，建议继续积累样本后再细调'})

    weakest_item = None
    completed_items = [item for item in stock_items if item.get('completed', 0) >= 4]
    if completed_items:
        weakest_item = min(completed_items, key=lambda item: (item.get('win_rate', 0.0), item.get('avg_profit_pct', 0.0), -item.get('completed', 0)))
    if weakest_item and weakest_item.get('code') != normalized_focus_code:
        suggestions.append({'level': 'info', 'msg': f"{weakest_item.get('name') or weakest_item.get('code')} 是当前拖后腿标的，可优先限制其新信号"})

    return {
        'summary': overall,
        'stocks': stock_items,
        'focus': focus_item,
        'suggestions': suggestions
    }
