import copy
import datetime
import time

from flask import Blueprint, jsonify, request

from renfu.request_args import parse_int_value


def register_runtime_routes(
    app,
    *,
    parse_since_ts_arg,
    to_bool,
    build_data_payload,
    state_lock,
    health_state,
    active_stocks,
    pending_signals,
    risk_state,
    is_risk_paused,
    is_trading_time,
    build_periodic_report
):
    bp = Blueprint('runtime_routes', __name__)

    @bp.route('/api/data')
    def api_data_route():
        since_ts = parse_since_ts_arg(request.args.get('since_ts'))
        force_full = to_bool(request.args.get('full', '0'))
        return jsonify(build_data_payload(since_ts=since_ts, force_full=force_full))

    @bp.route('/api/health')
    def api_health_route():
        now_ts = time.time()
        with state_lock:
            health_snapshot = copy.deepcopy(health_state)
            active_codes = list(active_stocks.keys())
            pending_n = len(pending_signals)
            risk_snapshot = copy.deepcopy(risk_state)

        loop_age = now_ts - float(health_snapshot.get('last_loop_ts') or 0.0) if health_snapshot.get('last_loop_ts') else None
        fetch_age = now_ts - float(health_snapshot.get('last_fetch_ok_ts') or 0.0) if health_snapshot.get('last_fetch_ok_ts') else None
        paused, left_sec, reason = is_risk_paused()

        status = 'ok'
        alerts = list(health_snapshot.get('alerts', []))
        if loop_age is not None and loop_age > 30:
            alerts.append({'level': 'warn', 'msg': f'worker loop age {loop_age:.1f}s'})
        if fetch_age is not None and is_trading_time() and fetch_age > 120:
            alerts.append({'level': 'warn', 'msg': f'fetch age {fetch_age:.1f}s'})
        if paused:
            alerts.append({'level': 'warn', 'msg': f'risk paused {left_sec:.1f}s ({reason})'})
        if alerts:
            status = 'warn'

        return jsonify({
            'status': status,
            'ts': datetime.datetime.now().isoformat(timespec='seconds'),
            'is_trading': is_trading_time(),
            'active_codes': active_codes,
            'pending_signals': pending_n,
            'worker_loop_age_sec': round(loop_age, 2) if loop_age is not None else None,
            'last_fetch_age_sec': round(fetch_age, 2) if fetch_age is not None else None,
            'health': health_snapshot,
            'risk': risk_snapshot,
            'risk_paused': paused,
            'risk_pause_left_sec': round(left_sec, 2),
            'risk_pause_reason': reason,
            'alerts': alerts
        })

    @bp.route('/api/reports/periodic')
    def api_periodic_reports_route():
        weeks = parse_int_value(request.args.get('weeks', 8), 8, min_value=1, max_value=52)
        months = parse_int_value(request.args.get('months', 6), 6, min_value=1, max_value=24)
        report = build_periodic_report(weeks=weeks, months=months)
        return jsonify({'success': True, 'report': report})

    app.register_blueprint(bp)
