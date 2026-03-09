from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import MarketCache, PaperAccount, Signal, WatchlistItem
from app.models.entities import User


def build_dashboard_summary(db: Session, user: User) -> dict:
    pulse_rows = list(db.scalars(select(MarketCache).order_by(MarketCache.updated_at.desc()).limit(6)))
    signal_counts = {
        row[0]: row[1]
        for row in db.execute(
            select(Signal.status, func.count(Signal.id)).where(Signal.user_id == user.id).group_by(Signal.status)
        ).all()
    }
    paper = db.scalar(select(PaperAccount).where(PaperAccount.user_id == user.id))
    watchlist_count = db.scalar(select(func.count(WatchlistItem.id)).where(WatchlistItem.user_id == user.id)) or 0

    return {
        'user': user,
        'pulse': [
            {
                'symbol': row.symbol,
                'name': row.extra_json.get('name', row.symbol),
                'last_price': float(row.last_price),
                'change_pct': float(row.change_pct),
                'updated_at': row.updated_at,
            }
            for row in pulse_rows
        ],
        'watchlist_count': watchlist_count,
        'signal_counts': signal_counts,
        'paper_summary': {
            'starting_cash': float(paper.starting_cash) if paper else 0.0,
            'cash': float(paper.cash) if paper else 0.0,
            'realized_pnl': float(paper.realized_pnl) if paper else 0.0,
        },
        'alerts': [
            {'level': 'info', 'title': 'Legacy 已挂载', 'message': '旧系统可通过 /legacy 继续访问。'},
            {'level': 'info', 'title': '多用户隔离已启用', 'message': '当前 Dashboard 仅显示当前登录用户的数据。'},
        ],
    }


def build_diagnostics_overview(db: Session, user: User) -> dict:
    pending_count = db.scalar(select(func.count(Signal.id)).where(Signal.user_id == user.id, Signal.status == 'pending')) or 0
    success_count = db.scalar(select(func.count(Signal.id)).where(Signal.user_id == user.id, Signal.status == 'success')) or 0
    fail_count = db.scalar(select(func.count(Signal.id)).where(Signal.user_id == user.id, Signal.status == 'fail')) or 0
    total_closed = success_count + fail_count
    win_rate = round(success_count / total_closed * 100, 1) if total_closed else None

    return {
        'preflight': {
            'level': 'ok' if pending_count < 5 else 'warn',
            'pending_signals': pending_count,
            'message': '基础诊断已连通，新策略引擎接入后可替换为实时策略健康数据。',
        },
        'focus_guard': {
            'status': 'watch' if fail_count > success_count else 'normal',
            'summary': f'closed={total_closed}, win_rate={win_rate if win_rate is not None else "--"}%',
        },
        'rejection_monitor': {
            'top_reasons': ['risk_profile_gate', 'slot_guard', 'cooldown'] if total_closed else [],
            'total_rejected': fail_count,
        },
        'focus_review': {
            'recent_closed': total_closed,
            'success_count': success_count,
            'fail_count': fail_count,
        },
    }
