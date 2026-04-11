from flask import Blueprint, jsonify, request

from renfu.date_utils import is_valid_iso_date
from renfu.history_service import (
    VALID_SIGNAL_STATUS,
    query_signal_history
)
from renfu.request_args import parse_int_value


def register_management_routes(
    app,
    *,
    state_lock,
    market_data,
    to_bool,
    paper_start_cash,
    get_paper_snapshot,
    reset_paper_account,
    list_base_configs,
    upsert_base_config,
    seed_base_positions,
    apply_add_stock,
    apply_strategy_patch,
    log_debug_event,
    get_strategy_snapshot,
    list_param_versions,
    save_param_version,
    get_param_version,
    apply_remove_stock,
    get_latest_paper_orders_for_signal_ids,
    build_signal_execution_summary,
    get_db,
    send_test_notification
):
    bp = Blueprint('management_routes', __name__)

    @bp.route('/api/paper/account')
    def api_paper_account_route():
        with state_lock:
            current_state = {}
            for code, data_list in market_data.items():
                if data_list:
                    current_state[code] = {'price': data_list[-1].get('price', 0.0)}
        limit = parse_int_value(request.args.get('limit', 30), 30, min_value=1, max_value=500)
        snapshot = get_paper_snapshot(current_state, recent_limit=limit)
        return jsonify({'success': True, 'paper': snapshot})

    @bp.route('/api/paper/reset', methods=['POST'])
    def api_paper_reset_route():
        data = request.get_json(silent=True) or {}
        confirm = to_bool(data.get('confirm', False))
        if not confirm:
            return jsonify({'success': False, 'msg': 'missing confirm=true'})
        try:
            starting_cash = float(data.get('starting_cash', paper_start_cash))
        except Exception:
            starting_cash = paper_start_cash
        reset_paper_account(starting_cash=starting_cash)
        snapshot = get_paper_snapshot({}, recent_limit=20)
        return jsonify({'success': True, 'paper': snapshot})

    @bp.route('/api/paper/base-config', methods=['GET'])
    def api_paper_base_config_list_route():
        return jsonify({'success': True, 'items': list_base_configs()})

    @bp.route('/api/paper/base-config', methods=['POST'])
    def api_paper_base_config_upsert_route():
        data = request.get_json(silent=True) or {}
        items = data.get('items')
        if not isinstance(items, list):
            items = [data]
        results = []
        for item in items:
            ok, msg = upsert_base_config(
                item.get('code'),
                item.get('name', ''),
                item.get('base_amount', 0.0),
                item.get('base_cost_line', 0.0),
                enabled=to_bool(item.get('enabled', True)),
                t_order_amount=item.get('t_order_amount', 0.0),
                t_daily_budget=item.get('t_daily_budget', 0.0),
                t_costline_strength=item.get('t_costline_strength', 1.0)
            )
            results.append({
                'code': (item.get('code') or '').lower(),
                'success': ok,
                'msg': msg
            })

        apply_seed = to_bool(data.get('apply_seed', False))
        reseed = to_bool(data.get('reseed', False))
        applied = []
        if apply_seed:
            applied = seed_base_positions(reseed=reseed)
        snapshot = get_paper_snapshot({}, recent_limit=20)
        return jsonify({
            'success': all(r['success'] for r in results),
            'results': results,
            'applied': applied,
            'paper': snapshot
        })

    @bp.route('/api/paper/base-config/seed', methods=['POST'])
    def api_paper_base_seed_route():
        data = request.get_json(silent=True) or {}
        reseed = to_bool(data.get('reseed', False))
        applied = seed_base_positions(reseed=reseed)
        snapshot = get_paper_snapshot({}, recent_limit=20)
        return jsonify({'success': True, 'applied': applied, 'paper': snapshot})

    @bp.route('/api/stocks', methods=['POST'])
    def api_add_stock_route():
        payload = request.get_json(silent=True) or {}
        code = payload.get('code', '').strip().lower()
        success, msg = apply_add_stock(code)
        return jsonify({'success': success, 'msg': msg})

    @bp.route('/api/config', methods=['POST'])
    def update_config_route():
        data = request.get_json(silent=True) or {}
        try:
            ok, errors, applied = apply_strategy_patch(data)
            if not ok:
                log_debug_event('config_update_failed', {'changes': data, 'errors': errors})
                return jsonify({'success': False, 'msg': 'invalid config', 'errors': errors})

            log_debug_event(
                'config_updated',
                {
                    'changes': applied,
                    'strategy': get_strategy_snapshot()
                }
            )

            return jsonify({'success': True, 'applied': applied})
        except Exception as e:
            log_debug_event('config_update_failed', {'changes': data, 'error': str(e)})
            return jsonify({'success': False, 'msg': str(e)})

    @bp.route('/api/config', methods=['GET'])
    def api_get_config_route():
        return jsonify({
            'success': True,
            'strategy': get_strategy_snapshot()
        })

    @bp.route('/api/config/snapshots', methods=['GET'])
    def api_list_config_snapshots_route():
        limit = parse_int_value(request.args.get('limit', 30), 30, min_value=1, max_value=365)
        items = list_param_versions(limit=limit)
        return jsonify({'success': True, 'items': items})

    @bp.route('/api/config/snapshots', methods=['POST'])
    def api_save_config_snapshot_route():
        data = request.get_json(silent=True) or {}
        note = data.get('note', '')
        version_id, snapshot = save_param_version(note=note)
        log_debug_event(
            'config_snapshot_saved',
            {'version_id': version_id, 'note': note, 'strategy': snapshot}
        )
        return jsonify({'success': True, 'id': version_id, 'note': note, 'params': snapshot})

    @bp.route('/api/config/rollback', methods=['POST'])
    def api_config_rollback_route():
        data = request.get_json(silent=True) or {}
        version_id = data.get('id')
        if version_id is None:
            return jsonify({'success': False, 'msg': 'missing id'})
        try:
            version_id = int(version_id)
        except Exception:
            return jsonify({'success': False, 'msg': 'invalid id'})

        version = get_param_version(version_id)
        if not version:
            return jsonify({'success': False, 'msg': f'param version not found: {version_id}'})

        ok, errors, applied = apply_strategy_patch(version.get('params', {}))
        if not ok:
            log_debug_event(
                'config_rollback_failed',
                {'version_id': version_id, 'errors': errors, 'raw_params': version.get('params', {})}
            )
            return jsonify({'success': False, 'msg': 'rollback apply failed', 'errors': errors})

        log_debug_event(
            'config_rollback_applied',
            {
                'version_id': version_id,
                'note': version.get('note', ''),
                'changes': applied,
                'strategy': get_strategy_snapshot()
            }
        )
        return jsonify({
            'success': True,
            'version_id': version_id,
            'note': version.get('note', ''),
            'applied': applied
        })

    @bp.route('/api/stocks/<code>', methods=['DELETE'])
    def api_remove_stock_route(code):
        success, msg = apply_remove_stock(code.lower())
        status = 200 if success else 400
        return jsonify({'success': success, 'msg': msg}), status

    @bp.route('/api/notify/test', methods=['POST'])
    def api_notify_test_route():
        data = request.get_json(silent=True) or {}
        title = str(data.get('title') or '测试通知').strip()
        body = str(data.get('body') or '').strip()
        success, msg = send_test_notification(title=title, body=body)
        status = 200 if success else 400
        return jsonify({'success': success, 'msg': msg}), status

    @bp.route('/api/history')
    def api_history_route():
        conn = None
        try:
            conn = get_db()
            date_q = request.args.get('date')
            code_q = (request.args.get('code') or '').strip().lower()
            status_q = (request.args.get('status') or '').strip().lower()
            days_q = parse_int_value(request.args.get('days', 7), 7, min_value=1, max_value=365)
            limit_q = parse_int_value(request.args.get('limit', 500), 500, min_value=1, max_value=5000)

            if date_q and not is_valid_iso_date(date_q):
                return jsonify({'success': False, 'msg': f'invalid date: {date_q}, expected YYYY-MM-DD'}), 400
            if status_q and status_q not in VALID_SIGNAL_STATUS:
                return jsonify({'success': False, 'msg': f'invalid status: {status_q}'}), 400

            payload = query_signal_history(
                conn,
                date_q=date_q,
                days_q=days_q,
                code_q=code_q,
                status_q=status_q,
                limit_q=limit_q
            )
            signal_ids = [item.get('id') for item in (payload.get('signals') or [])]
            paper_map = get_latest_paper_orders_for_signal_ids(signal_ids)
            if paper_map:
                for item in payload.get('signals') or []:
                    sig_id = str(item.get('id') or '').strip()
                    if sig_id and sig_id in paper_map:
                        item['paper'] = paper_map[sig_id]
            payload['execution'] = build_signal_execution_summary(payload.get('signals') or [], paper_map=paper_map)
            return jsonify(payload)
        except Exception as e:
            return jsonify({'success': False, 'msg': str(e)}), 500
        finally:
            if conn is not None:
                conn.close()

    app.register_blueprint(bp)
