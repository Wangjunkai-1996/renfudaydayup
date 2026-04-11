from __future__ import annotations

from datetime import date, datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


class ApiMessage(BaseModel):
    success: bool = True
    message: str = 'ok'


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    username: str
    role: str
    is_active: bool
    created_at: datetime
    updated_at: datetime


class MarketPulseItem(BaseModel):
    symbol: str
    name: str
    last_price: float
    change_pct: float
    updated_at: Optional[datetime] = None


class WatchlistItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    symbol: str
    display_name: str
    notes: str
    sort_order: int
    created_at: datetime


class StrategyConfigOut(BaseModel):
    id: str
    user_id: str
    config_json: dict[str, Any]
    updated_at: datetime


class StrategySnapshotOut(BaseModel):
    id: str
    label: str
    config_json: dict[str, Any]
    created_at: datetime


class SignalOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    symbol: str
    name: str
    side: str
    level: str
    price: float
    status: str
    description: str
    occurred_at: datetime
    resolved_at: Optional[datetime] = None
    meta_json: dict[str, Any] = Field(default_factory=dict)


class SignalExplanationOut(BaseModel):
    signal_id: str
    summary: str
    factors_json: list[Any]
    updated_at: datetime


class PaperAccountOut(BaseModel):
    id: str
    user_id: str
    starting_cash: float
    cash: float
    realized_pnl: float
    updated_at: datetime


class PaperPositionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    symbol: str
    name: str
    quantity: int
    available_quantity: int
    avg_cost: float
    last_price: float
    updated_at: datetime


class PaperOrderOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    signal_id: Optional[str]
    symbol: str
    side: str
    status: str
    quantity: int
    price: float
    reason: str
    created_at: datetime


class PaperBaseConfigOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    symbol: str
    base_amount: float
    base_cost: float
    t_order_amount: float
    t_daily_budget: float
    t_costline_strength: float
    enabled: bool
    updated_at: datetime


class DailyReportOut(BaseModel):
    id: str
    trade_date: date
    title: str
    content_json: dict[str, Any]
    created_at: datetime


class PeriodicReportOut(BaseModel):
    id: str
    period_kind: str
    period_key: str
    content_json: dict[str, Any]
    created_at: datetime


class DashboardSummary(BaseModel):
    user: UserOut
    pulse: list[MarketPulseItem]
    watchlist_count: int
    signal_counts: dict[str, int]
    paper_summary: dict[str, Any]
    alerts: list[dict[str, Any]] = Field(default_factory=list)
    workbench: Optional[dict[str, Any]] = None


class DiagnosticsOverview(BaseModel):
    preflight: dict[str, Any]
    focus_guard: dict[str, Any]
    rejection_monitor: dict[str, Any]
    focus_review: dict[str, Any]


class NotificationSettingsOut(BaseModel):
    settings_json: dict[str, Any] = Field(default_factory=dict)


class AdminUserCreate(BaseModel):
    username: str
    password: str
    role: str = 'user'


class AdminPasswordReset(BaseModel):
    password: str


class AdminUserStateUpdate(BaseModel):
    is_active: bool
