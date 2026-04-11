from datetime import date, datetime
from typing import Optional

from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class User(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = 'users'

    username: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(16), default='user', nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_login_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    sessions: Mapped[list['UserSession']] = relationship(back_populates='user', cascade='all, delete-orphan')


class UserSession(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = 'user_sessions'

    user_id: Mapped[str] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), index=True, nullable=False)
    refresh_token_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    user_agent: Mapped[Optional[str]] = mapped_column(String(255))
    ip_address: Mapped[Optional[str]] = mapped_column(String(64))

    user: Mapped['User'] = relationship(back_populates='sessions')


class WatchlistItem(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = 'watchlists'
    __table_args__ = (UniqueConstraint('user_id', 'symbol', name='uq_watchlists_user_symbol'),)

    user_id: Mapped[str] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), index=True, nullable=False)
    symbol: Mapped[str] = mapped_column(String(32), nullable=False)
    display_name: Mapped[str] = mapped_column(String(128), default='', nullable=False)
    notes: Mapped[str] = mapped_column(Text, default='', nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class StrategyConfig(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = 'strategy_configs'
    __table_args__ = (UniqueConstraint('user_id', name='uq_strategy_configs_user'),)

    user_id: Mapped[str] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), index=True, nullable=False)
    config_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)


class StrategySnapshot(UUIDPrimaryKeyMixin, Base):
    __tablename__ = 'strategy_snapshots'

    user_id: Mapped[str] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), index=True, nullable=False)
    label: Mapped[str] = mapped_column(String(128), nullable=False)
    config_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class Signal(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = 'signals'

    user_id: Mapped[str] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), index=True, nullable=False)
    symbol: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(128), default='', nullable=False)
    side: Mapped[str] = mapped_column(String(16), nullable=False)
    level: Mapped[str] = mapped_column(String(32), default='normal', nullable=False)
    price: Mapped[float] = mapped_column(Float, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default='pending', nullable=False)
    description: Mapped[str] = mapped_column(Text, default='', nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    meta_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)


class SignalEvent(UUIDPrimaryKeyMixin, Base):
    __tablename__ = 'signal_events'

    signal_id: Mapped[str] = mapped_column(ForeignKey('signals.id', ondelete='CASCADE'), index=True, nullable=False)
    event_type: Mapped[str] = mapped_column(String(32), nullable=False)
    payload_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class SignalExplanation(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = 'signal_explanations'
    __table_args__ = (UniqueConstraint('signal_id', name='uq_signal_explanations_signal'),)

    signal_id: Mapped[str] = mapped_column(ForeignKey('signals.id', ondelete='CASCADE'), nullable=False)
    summary: Mapped[str] = mapped_column(Text, default='', nullable=False)
    factors_json: Mapped[list] = mapped_column(JSON, default=list, nullable=False)


class PaperAccount(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = 'paper_accounts'
    __table_args__ = (UniqueConstraint('user_id', name='uq_paper_accounts_user'),)

    user_id: Mapped[str] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), index=True, nullable=False)
    starting_cash: Mapped[float] = mapped_column(Numeric(18, 2), default=800000, nullable=False)
    cash: Mapped[float] = mapped_column(Numeric(18, 2), default=800000, nullable=False)
    realized_pnl: Mapped[float] = mapped_column(Numeric(18, 2), default=0, nullable=False)


class PaperPosition(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = 'paper_positions'

    user_id: Mapped[str] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), index=True, nullable=False)
    symbol: Mapped[str] = mapped_column(String(32), nullable=False)
    name: Mapped[str] = mapped_column(String(128), default='', nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    available_quantity: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    avg_cost: Mapped[float] = mapped_column(Numeric(18, 4), default=0, nullable=False)
    last_price: Mapped[float] = mapped_column(Numeric(18, 4), default=0, nullable=False)


class PaperOrder(UUIDPrimaryKeyMixin, Base):
    __tablename__ = 'paper_orders'

    user_id: Mapped[str] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), index=True, nullable=False)
    signal_id: Mapped[Optional[str]] = mapped_column(ForeignKey('signals.id', ondelete='SET NULL'))
    symbol: Mapped[str] = mapped_column(String(32), nullable=False)
    side: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default='created', nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    price: Mapped[float] = mapped_column(Numeric(18, 4), default=0, nullable=False)
    reason: Mapped[str] = mapped_column(Text, default='', nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class PaperBaseConfig(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = 'paper_base_configs'
    __table_args__ = (UniqueConstraint('user_id', 'symbol', name='uq_paper_base_configs_user_symbol'),)

    user_id: Mapped[str] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), index=True, nullable=False)
    symbol: Mapped[str] = mapped_column(String(32), nullable=False)
    base_amount: Mapped[float] = mapped_column(Numeric(18, 2), default=0, nullable=False)
    base_cost: Mapped[float] = mapped_column(Numeric(18, 4), default=0, nullable=False)
    t_order_amount: Mapped[float] = mapped_column(Numeric(18, 2), default=0, nullable=False)
    t_daily_budget: Mapped[float] = mapped_column(Numeric(18, 2), default=0, nullable=False)
    t_costline_strength: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class DailyReport(UUIDPrimaryKeyMixin, Base):
    __tablename__ = 'daily_reports'
    __table_args__ = (UniqueConstraint('user_id', 'trade_date', name='uq_daily_reports_user_trade_date'),)

    user_id: Mapped[str] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), index=True, nullable=False)
    trade_date: Mapped[date] = mapped_column(Date, nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    content_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class DailyReportBundle(UUIDPrimaryKeyMixin, Base):
    __tablename__ = 'daily_report_bundles'

    user_id: Mapped[str] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), index=True, nullable=False)
    trade_date: Mapped[date] = mapped_column(Date, nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    content_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class PeriodicReport(UUIDPrimaryKeyMixin, Base):
    __tablename__ = 'periodic_reports'
    __table_args__ = (UniqueConstraint('user_id', 'period_kind', 'period_key', name='uq_periodic_reports_user_period'),)

    user_id: Mapped[str] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), index=True, nullable=False)
    period_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    period_key: Mapped[str] = mapped_column(String(64), nullable=False)
    content_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class TuningHistory(UUIDPrimaryKeyMixin, Base):
    __tablename__ = 'tuning_history'

    user_id: Mapped[str] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), index=True, nullable=False)
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    patch_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    note: Mapped[str] = mapped_column(Text, default='', nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class NotificationSetting(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = 'notification_settings'
    __table_args__ = (UniqueConstraint('user_id', name='uq_notification_settings_user'),)

    user_id: Mapped[str] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), index=True, nullable=False)
    settings_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)


class AuditLog(UUIDPrimaryKeyMixin, Base):
    __tablename__ = 'audit_logs'

    user_id: Mapped[Optional[str]] = mapped_column(ForeignKey('users.id', ondelete='SET NULL'), index=True)
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    resource_type: Mapped[str] = mapped_column(String(64), nullable=False)
    resource_id: Mapped[Optional[str]] = mapped_column(String(64))
    detail_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class MarketInstrument(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = 'market_instruments'

    symbol: Mapped[str] = mapped_column(String(32), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    exchange: Mapped[str] = mapped_column(String(32), default='CN', nullable=False)
    sector: Mapped[str] = mapped_column(String(128), default='', nullable=False)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)


class MarketCache(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = 'market_cache'

    symbol: Mapped[str] = mapped_column(String(32), unique=True, index=True, nullable=False)
    last_price: Mapped[float] = mapped_column(Numeric(18, 4), default=0, nullable=False)
    change_pct: Mapped[float] = mapped_column(Float, default=0, nullable=False)
    open_price: Mapped[float] = mapped_column(Numeric(18, 4), default=0, nullable=False)
    prev_close: Mapped[float] = mapped_column(Numeric(18, 4), default=0, nullable=False)
    volume: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    market_time: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    source: Mapped[str] = mapped_column(String(32), default='seed', nullable=False)
    extra_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)


class TradeCalendarCache(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = 'trade_calendar_cache'

    calendar_date: Mapped[date] = mapped_column(Date, unique=True, nullable=False)
    is_trading_day: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    market: Mapped[str] = mapped_column(String(32), default='CN', nullable=False)
    extra_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
