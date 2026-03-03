import datetime
import json
import os

from flask import Blueprint, jsonify, request


def register_report_routes(
    app,
    *,
    to_bool,
    normalize_date_str,
    get_default_baseline_date,
    read_debug_log_entries,
    summarize_debug_entries,
    read_daily_report_json,
    get_daily_report_paths,
    generate_daily_report,
    get_daily_bundle_path,
    read_daily_bundle_json,
    generate_daily_bundle,
    get_or_generate_daily_report,
    compare_reports,
    build_preflight_assessment,
    compute_slot_performance,
    build_slot_hints,
    build_param_suggestion,
    save_tuning_suggestion,
    apply_strategy_patch,
    save_param_version,
    log_debug_event,
    get_strategy_snapshot,
    report_dir,
    tuning_dir,
    get_db,
    build_signal_explanation
):
    bp = Blueprint('report_routes', __name__)

    @bp.route('/api/debug/logs')
    def api_debug_logs_route():
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

    @bp.route('/api/debug/summary')
    def api_debug_summary_route():
        date_q = request.args.get('date') or datetime.datetime.now().strftime('%Y-%m-%d')
        entries = read_debug_log_entries(date_q, limit=5000)
        summary = summarize_debug_entries(entries)
        summary['date'] = date_q
        return jsonify(summary)

    @bp.route('/api/reports/daily')
    def api_get_daily_report_route():
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

    @bp.route('/api/reports/daily/generate', methods=['POST'])
    def api_generate_daily_report_route():
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

    @bp.route('/api/reports/daily/list')
    def api_list_daily_reports_route():
        os.makedirs(report_dir, exist_ok=True)
        try:
            limit = int(request.args.get('limit', 30))
        except Exception:
            limit = 30
        limit = max(1, min(limit, 365))

        files = [f for f in os.listdir(report_dir) if f.endswith('.json')]
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

    @bp.route('/api/reports/daily/bundle')
    def api_get_daily_bundle_route():
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

    @bp.route('/api/reports/daily/bundle/generate', methods=['POST'])
    def api_generate_daily_bundle_route():
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

    @bp.route('/api/reports/daily/compare')
    def api_compare_daily_reports_route():
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

    @bp.route('/api/preflight')
    def api_preflight_route():
        try:
            lookback = int(request.args.get('lookback', 5))
        except Exception:
            lookback = 5
        date_q = request.args.get('date')
        assessment = build_preflight_assessment(ref_date=date_q, lookback_days=lookback)
        return jsonify({'success': True, 'assessment': assessment})

    @bp.route('/api/analytics/slot-performance')
    def api_slot_performance_route():
        try:
            days = int(request.args.get('days', 10))
        except Exception:
            days = 10
        end_date = request.args.get('date')
        perf = compute_slot_performance(days=days, end_date=end_date)
        hints = build_slot_hints(perf)
        return jsonify({'success': True, 'performance': perf, 'hints': hints})

    @bp.route('/api/tuning/suggest')
    def api_tuning_suggest_route():
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

    @bp.route('/api/tuning/apply', methods=['POST'])
    def api_tuning_apply_route():
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

    @bp.route('/api/tuning/history')
    def api_tuning_history_route():
        os.makedirs(tuning_dir, exist_ok=True)
        try:
            limit = int(request.args.get('limit', 30))
        except Exception:
            limit = 30
        limit = max(1, min(limit, 365))

        files = [f for f in os.listdir(tuning_dir) if f.endswith('.json')]
        files.sort(reverse=True)
        items = []
        for name in files[:limit]:
            path = os.path.join(tuning_dir, name)
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

    @bp.route('/api/signals/<sig_id>/explain')
    def api_signal_explain_route(sig_id):
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

    app.register_blueprint(bp)

