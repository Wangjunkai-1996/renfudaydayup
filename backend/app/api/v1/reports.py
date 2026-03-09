from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db
from app.core.deps import get_current_user
from app.domain.legacy_facade import (
    build_legacy_periodic_report,
    can_use_legacy_bridge,
    compare_legacy_daily_reports,
    generate_legacy_bundle,
    generate_legacy_daily_report,
    get_legacy_bundle,
    get_legacy_daily_report,
    list_legacy_daily_reports,
    query_legacy_history,
)
from app.models import DailyReport, DailyReportBundle, PeriodicReport, Signal
from app.schemas.common import DailyReportOut, PeriodicReportOut
from app.schemas.inputs import BundleGenerateRequest, DailyReportGenerateRequest


router = APIRouter(prefix='/reports', tags=['reports'])


def _use_legacy(current_user) -> bool:
    settings = get_settings()
    return can_use_legacy_bridge(username=current_user.username, bootstrap_username=settings.bootstrap_admin_username)


@router.get('/history')
def report_history(
    date: Optional[str] = Query(default=None),
    days: int = Query(default=14, ge=1, le=365),
    code: str = Query(default=''),
    status_filter: Optional[str] = Query(default=None, alias='status'),
    limit: int = Query(default=500, ge=1, le=5000),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    if _use_legacy(current_user):
        payload = query_legacy_history(
            date_q=date,
            days_q=days,
            code_q=code.strip().lower(),
            status_q=(status_filter or '').strip(),
            limit_q=limit,
        )
        payload['source'] = 'legacy'
        return payload

    stmt = select(Signal).where(Signal.user_id == current_user.id)
    if date:
        stmt = stmt.where(func.date(Signal.occurred_at) == date)
    if code:
        stmt = stmt.where(Signal.symbol == code.strip().lower())
    if status_filter:
        stmt = stmt.where(Signal.status == status_filter)
    rows = list(db.scalars(stmt.order_by(desc(Signal.occurred_at)).limit(limit)))
    daily_stats = []
    grouped = {}
    for row in rows:
        key = row.occurred_at.date().isoformat()
        bucket = grouped.setdefault(key, {'date': key, 'total': 0, 'success': 0, 'fail': 0})
        bucket['total'] += 1
        if row.status == 'success':
            bucket['success'] += 1
        elif row.status == 'fail':
            bucket['fail'] += 1
    for bucket in grouped.values():
        closed = bucket['success'] + bucket['fail']
        bucket['win_rate'] = round(bucket['success'] / closed * 100, 1) if closed else 0
        daily_stats.append(bucket)
    daily_stats.sort(key=lambda item: item['date'], reverse=True)
    return {
        'success': True,
        'source': 'next',
        'query': {'date': date, 'days': days, 'code': code or None, 'status': status_filter, 'limit': limit},
        'signals': [
            {
                'id': row.id,
                'date': row.occurred_at.date().isoformat(),
                'time': row.occurred_at.strftime('%H:%M:%S'),
                'code': row.symbol,
                'name': row.name,
                'type': row.side,
                'level': row.level,
                'price': float(row.price),
                'status': row.status,
                'desc': row.description,
            }
            for row in rows
        ],
        'daily_stats': daily_stats[:days],
    }


@router.get('/daily')
def get_daily_report(date: str, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    if _use_legacy(current_user):
        return get_legacy_daily_report(target_date=date, generate_if_missing=True)

    row = db.scalar(select(DailyReport).where(DailyReport.user_id == current_user.id, DailyReport.trade_date == date))
    return {
        'success': row is not None,
        'date': date,
        'report': None if row is None else DailyReportOut(id=row.id, trade_date=row.trade_date, title=row.title, content_json=row.content_json, created_at=row.created_at).model_dump(),
        'json_path': None,
        'md_path': None,
        'source': 'next',
    }


@router.post('/daily/generate', status_code=status.HTTP_201_CREATED)
def generate_daily_report(payload: DailyReportGenerateRequest, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    if _use_legacy(current_user):
        return generate_legacy_daily_report(target_date=payload.trade_date.isoformat())

    signals = list(db.scalars(select(Signal).where(Signal.user_id == current_user.id, func.date(Signal.occurred_at) == payload.trade_date.isoformat())))
    row = db.scalar(select(DailyReport).where(DailyReport.user_id == current_user.id, DailyReport.trade_date == payload.trade_date))
    content = {
        'trade_date': payload.trade_date.isoformat(),
        'signal_total': len(signals),
        'success_count': sum(1 for item in signals if item.status == 'success'),
        'fail_count': sum(1 for item in signals if item.status == 'fail'),
    }
    if row is None:
        row = DailyReport(
            user_id=current_user.id,
            trade_date=payload.trade_date,
            title=f'{payload.trade_date.isoformat()} 日报',
            content_json=content,
            created_at=datetime.now(timezone.utc),
        )
        db.add(row)
    else:
        row.content_json = content
        row.title = f'{payload.trade_date.isoformat()} 日报'
    db.commit()
    db.refresh(row)
    return {'success': True, 'date': payload.trade_date.isoformat(), 'report': DailyReportOut(id=row.id, trade_date=row.trade_date, title=row.title, content_json=row.content_json, created_at=row.created_at).model_dump(), 'json_path': None, 'md_path': None, 'source': 'next'}


@router.get('/daily/list')
def list_daily_reports(limit: int = Query(default=30, ge=1, le=365), db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    if _use_legacy(current_user):
        payload = list_legacy_daily_reports(limit=limit)
        payload['source'] = 'legacy'
        return payload

    rows = list(db.scalars(select(DailyReport).where(DailyReport.user_id == current_user.id).order_by(desc(DailyReport.trade_date)).limit(limit)))
    return {'success': True, 'source': 'next', 'items': [DailyReportOut(id=row.id, trade_date=row.trade_date, title=row.title, content_json=row.content_json, created_at=row.created_at).model_dump() for row in rows]}


@router.get('/daily/bundle')
def get_bundle(date: str, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    if _use_legacy(current_user):
        payload = get_legacy_bundle(target_date=date, generate_if_missing=True)
        payload['source'] = 'legacy'
        return payload

    row = db.scalar(select(DailyReportBundle).where(DailyReportBundle.user_id == current_user.id, DailyReportBundle.trade_date == date))
    return {'success': row is not None, 'date': date, 'bundle': None if row is None else {'id': row.id, 'trade_date': row.trade_date, 'title': row.title, 'content_json': row.content_json}, 'path': None, 'source': 'next'}


@router.post('/daily/bundle/generate')
def generate_bundle(payload: BundleGenerateRequest, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    if _use_legacy(current_user):
        payload_out = generate_legacy_bundle(target_date=payload.trade_date.isoformat())
        payload_out['source'] = 'legacy'
        return payload_out

    daily = db.scalar(select(DailyReport).where(DailyReport.user_id == current_user.id, DailyReport.trade_date == payload.trade_date))
    if daily is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Daily report not found')
    bundle = db.scalar(select(DailyReportBundle).where(DailyReportBundle.user_id == current_user.id, DailyReportBundle.trade_date == payload.trade_date))
    content = {'daily_report_id': daily.id, 'highlights': daily.content_json, 'generated_from': 'new-stack'}
    if bundle is None:
        bundle = DailyReportBundle(
            user_id=current_user.id,
            trade_date=payload.trade_date,
            title=f'{payload.trade_date.isoformat()} Bundle',
            content_json=content,
            created_at=datetime.now(timezone.utc),
        )
        db.add(bundle)
    else:
        bundle.content_json = content
    db.commit()
    db.refresh(bundle)
    return {'success': True, 'date': payload.trade_date.isoformat(), 'bundle': {'id': bundle.id, 'title': bundle.title, 'content_json': bundle.content_json}, 'path': None, 'source': 'next'}


@router.get('/daily/compare')
def compare_daily(current_date: str, baseline_date: Optional[str] = None, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    if _use_legacy(current_user):
        payload = compare_legacy_daily_reports(target_date=current_date, baseline_date=baseline_date)
        payload['source'] = 'legacy'
        return payload

    if not baseline_date:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='baseline_date required for next reports')
    current = db.scalar(select(DailyReport).where(DailyReport.user_id == current_user.id, DailyReport.trade_date == current_date))
    baseline = db.scalar(select(DailyReport).where(DailyReport.user_id == current_user.id, DailyReport.trade_date == baseline_date))
    if current is None or baseline is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Report not found')
    current_total = int(current.content_json.get('signal_total', 0))
    baseline_total = int(baseline.content_json.get('signal_total', 0))
    return {
        'success': True,
        'source': 'next',
        'comparison': {
            'current_date': current_date,
            'baseline_date': baseline_date,
            'signal_total_delta': current_total - baseline_total,
            'current': current.content_json,
            'baseline': baseline.content_json,
        },
    }


@router.get('/periodic')
def list_periodic_reports(
    weeks: int = Query(default=8, ge=1, le=52),
    months: int = Query(default=6, ge=1, le=24),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    if _use_legacy(current_user):
        return {'success': True, 'source': 'legacy', 'report': build_legacy_periodic_report(weeks=weeks, months=months)}

    rows = list(db.scalars(select(PeriodicReport).where(PeriodicReport.user_id == current_user.id).order_by(desc(PeriodicReport.created_at)).limit(24)))
    return {'success': True, 'source': 'next', 'items': [PeriodicReportOut(id=row.id, period_kind=row.period_kind, period_key=row.period_key, content_json=row.content_json, created_at=row.created_at).model_dump() for row in rows]}
