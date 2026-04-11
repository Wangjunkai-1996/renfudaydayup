export interface User {
  id: string;
  username: string;
  role: 'admin' | 'user';
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface AlertItem {
  level: string;
  title: string;
  message: string;
}

export interface MarketPulseItem {
  symbol: string;
  name: string;
  last_price: number;
  change_pct: number;
  updated_at?: string;
}

export interface MarketSeriesPoint {
  time: string;
  price: number;
  vwap: number;
  ts?: number;
}

export interface MarketAnnotations {
  prev_close?: number | null;
  open_price?: number | null;
  limit_up?: number | null;
  limit_down?: number | null;
  r_breaker?: Record<string, number>;
}

export interface NewsItem {
  title: string;
  summary: string;
  url: string;
  source: string;
  time: string;
}

export interface InstrumentContext {
  trend: string;
  industry: string;
  news: NewsItem[];
}

export interface WorkbenchItem {
  symbol: string;
  name: string;
  market: {
    last_price: number;
    change_pct: number;
    vwap?: number;
    open_price?: number;
    prev_close?: number;
    updated_at?: string;
  };
  series: MarketSeriesPoint[];
  annotations: MarketAnnotations;
  context: InstrumentContext;
}

export interface MarketWorkbenchPayload {
  symbols: string[];
  active_symbol: string | null;
  items: WorkbenchItem[];
  source: string;
  updated_at?: string;
}

export interface DashboardSummary {
  user: User;
  pulse: MarketPulseItem[];
  watchlist_count: number;
  signal_counts: Record<string, number>;
  paper_summary: {
    starting_cash: number;
    cash: number;
    realized_pnl: number;
    market_value?: number;
    nav?: number;
    return_pct?: number;
  };
  alerts: AlertItem[];
  workbench?: MarketWorkbenchPayload;
}

export interface DiagnosticsOverview {
  preflight: {
    headline?: string;
    details?: Record<string, unknown>;
    [key: string]: unknown;
  };
  focus_guard: {
    headline?: string;
    summary?: string;
    raw?: Record<string, unknown>;
    [key: string]: unknown;
  };
  rejection_monitor: {
    headline?: string;
    slot_hints?: string[];
    recent_closed?: number;
    win_rate?: number | null;
    raw?: Record<string, unknown>;
    [key: string]: unknown;
  };
  focus_review: {
    headline?: string;
    success_count?: number;
    fail_count?: number;
    raw?: Record<string, unknown>;
    [key: string]: unknown;
  };
}

export interface WatchlistItem {
  id: string;
  symbol: string;
  display_name: string;
  notes: string;
  sort_order: number;
  market?: {
    last_price: number | null;
    change_pct: number | null;
    updated_at?: string | null;
  };
}

export interface SignalItem {
  id: string;
  symbol: string;
  name: string;
  side: string;
  level: string;
  price: number;
  status: string;
  description: string;
  occurred_at: string;
  resolved_at?: string | null;
  meta_json: Record<string, unknown>;
}

export interface SignalExplainPayload {
  success: boolean;
  source: string;
  signal_id: string;
  signal?: SignalItem;
  explain: {
    summary?: string;
    factors_json?: Array<Record<string, unknown>>;
    updated_at?: string;
    signal?: Record<string, unknown>;
    slot?: string;
    factors?: string[];
    filter_meta?: Record<string, unknown>;
    strategy_snapshot?: Record<string, unknown>;
    accepted_event?: Record<string, unknown> | null;
    resolved_event?: Record<string, unknown> | null;
    lifecycle?: Array<Record<string, unknown>>;
    nearby_events?: Array<Record<string, unknown>>;
    chart_points?: MarketSeriesPoint[];
    insights?: string[];
  };
}

export interface PaperAccountView {
  id: string;
  user_id: string;
  starting_cash: number;
  cash: number;
  realized_pnl: number;
  market_value?: number;
  nav?: number;
  unrealized_pnl?: number;
  total_pnl?: number;
  return_pct?: number;
  updated_at?: string;
}

export interface PaperPositionView {
  id: string;
  symbol: string;
  name: string;
  quantity: number;
  available_quantity: number;
  avg_cost: number;
  last_price: number;
  market_value?: number;
  unrealized_pnl?: number;
  realized_pnl?: number;
  updated_at?: string;
}

export interface PaperOrderView {
  id: string;
  signal_id?: string | null;
  symbol: string;
  name?: string;
  side: string;
  status: string;
  quantity: number;
  price: number;
  amount?: number;
  fee?: number;
  reason: string;
  created_at: string;
}

export interface PaperBaseConfigView {
  id: string;
  symbol: string;
  name?: string;
  base_amount: number;
  base_cost: number;
  t_order_amount: number;
  t_daily_budget: number;
  t_costline_strength: number;
  enabled: boolean;
  updated_at: string;
  remaining_amount?: number;
  remaining_orders?: number;
}

export interface PaperAccountPayload {
  account: PaperAccountView;
  positions: PaperPositionView[];
  orders: PaperOrderView[];
  base_configs: PaperBaseConfigView[];
}

export interface ReportHistoryPayload {
  success: boolean;
  source: string;
  query?: Record<string, unknown>;
  signals: Array<Record<string, unknown>>;
  daily_stats: Array<Record<string, unknown>>;
  date_stats?: Record<string, unknown> | null;
}

export interface DailyReportListItem {
  date?: string;
  trade_date?: string;
  title?: string;
  json_path?: string;
  md_path?: string;
  exists_md?: boolean;
  id?: string;
}

export interface DailyReportPayload {
  success: boolean;
  date: string;
  report: Record<string, unknown> | null;
  json_path?: string | null;
  md_path?: string | null;
  source?: string;
}

export interface BundlePayload {
  success: boolean;
  date: string;
  bundle: Record<string, unknown> | null;
  path?: string | null;
  source?: string;
}

export interface ComparePayload {
  success: boolean;
  date: string;
  baseline_date: string;
  current_report?: Record<string, unknown>;
  baseline_report?: Record<string, unknown>;
  comparison?: Record<string, unknown>;
  source?: string;
}

export interface PeriodicReportPayload {
  success?: boolean;
  report?: Record<string, unknown>;
  [key: string]: unknown;
}

export interface TuningSuggestionPayload {
  success: boolean;
  source: string;
  assessment?: Record<string, unknown>;
  performance?: Record<string, unknown>;
  hints?: string[];
  diagnostics?: Record<string, unknown>;
  suggestion?: Record<string, unknown>;
  saved_path?: string;
}

export interface TuningHistoryItem {
  id?: string;
  action?: string;
  patch_json?: Record<string, unknown>;
  note?: string;
  created_at?: string;
  file?: string;
  path?: string;
  date?: string;
  baseline_date?: string;
  generated_at?: string;
  patch_size?: number;
}

export interface NotificationSettings {
  settings_json: Record<string, boolean | string | number>;
}

export interface HealthPayload {
  status: string;
  ts: string;
  components?: Record<string, string>;
}
