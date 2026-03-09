export interface User {
  id: string;
  username: string;
  role: 'admin' | 'user';
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface DashboardSummary {
  user: User;
  pulse: Array<{ symbol: string; name: string; last_price: number; change_pct: number; updated_at?: string }>;
  watchlist_count: number;
  signal_counts: Record<string, number>;
  paper_summary: { starting_cash: number; cash: number; realized_pnl: number };
  alerts: Array<{ level: string; title: string; message: string }>;
}

export interface DiagnosticsOverview {
  preflight: Record<string, unknown>;
  focus_guard: Record<string, unknown>;
  rejection_monitor: Record<string, unknown>;
  focus_review: Record<string, unknown>;
}
