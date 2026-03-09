from __future__ import annotations

from datetime import date
from typing import Any

from pydantic import BaseModel, Field


class WatchlistCreate(BaseModel):
    symbol: str
    display_name: str = ''
    notes: str = ''


class StrategyConfigUpdate(BaseModel):
    config_json: dict[str, Any] = Field(default_factory=dict)


class StrategySnapshotCreate(BaseModel):
    label: str


class StrategyRollbackRequest(BaseModel):
    snapshot_id: str


class PaperResetRequest(BaseModel):
    starting_cash: float = 800000


class PaperBaseConfigInput(BaseModel):
    symbol: str
    base_amount: float = 0
    base_cost: float = 0
    t_order_amount: float = 0
    t_daily_budget: float = 0
    t_costline_strength: float = 1.0
    enabled: bool = True


class PaperBaseConfigSeedRequest(BaseModel):
    symbols: list[str] = Field(default_factory=list)


class DailyReportGenerateRequest(BaseModel):
    trade_date: date


class BundleGenerateRequest(BaseModel):
    trade_date: date


class CompareRequest(BaseModel):
    current_date: date
    baseline_date: date


class TuningApplyRequest(BaseModel):
    patch: dict[str, Any] = Field(default_factory=dict)
    note: str = ''
