import collections


def summarize_debug_entries(entries):
    event_counts = collections.Counter()
    reject_reasons = collections.Counter()
    by_code = collections.defaultdict(lambda: {'accepted': 0, 'rejected': 0, 'resolved_success': 0, 'resolved_fail': 0})
    by_type = collections.defaultdict(lambda: {'accepted': 0, 'rejected': 0, 'resolved_success': 0, 'resolved_fail': 0})

    for entry in entries:
        event = entry.get('event', '')
        event_counts[event] += 1
        code = str(entry.get('code', ''))
        sig_type = str(entry.get('signal_type', ''))

        if event == 'signal_rejected':
            by_code[code]['rejected'] += 1
            by_type[sig_type]['rejected'] += 1
            for reason in entry.get('reasons') or []:
                reject_reasons[str(reason)] += 1
        elif event == 'signal_accepted':
            by_code[code]['accepted'] += 1
            by_type[sig_type]['accepted'] += 1
        elif event in ('signal_resolved', 'signal_force_closed'):
            status = entry.get('status')
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
