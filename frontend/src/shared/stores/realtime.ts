import type { DiagnosticsOverview, MarketPulseItem, SignalItem } from '@/shared/api/types';
import { defineStore } from 'pinia';

interface WatchlistQuote {
  symbol: string;
  name: string;
  last_price: number;
  change_pct: number;
}

const reconnectSteps = [1000, 2000, 5000, 10000, 20000];

export const useRealtimeStore = defineStore('realtime', {
  state: () => ({
    connected: false,
    connecting: false,
    pulse: [] as MarketPulseItem[],
    signals: [] as SignalItem[],
    watchlistQuotes: [] as WatchlistQuote[],
    diagnostics: null as DiagnosticsOverview | null,
    systemStatus: 'idle',
    isTrading: true,
    legacyMode: false,
    lastEventAt: '' as string,
    socket: null as WebSocket | null,
    reconnectAttempt: 0,
    manualClose: false,
  }),
  getters: {
    hasPulse(state) {
      return state.pulse.length > 0;
    },
    hasSignals(state) {
      return state.signals.length > 0;
    },
  },
  actions: {
    connect() {
      if (typeof window === 'undefined') {
        return;
      }
      if (this.socket && (this.socket.readyState === WebSocket.OPEN || this.socket.readyState === WebSocket.CONNECTING)) {
        return;
      }
      this.manualClose = false;
      this.connecting = true;
      const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
      const target = `${protocol}//${window.location.host}/ws/v1/stream`;
      const socket = new WebSocket(target);
      this.socket = socket;

      socket.onopen = () => {
        this.connected = true;
        this.connecting = false;
        this.reconnectAttempt = 0;
      };

      socket.onmessage = (event) => {
        const payload = JSON.parse(event.data) as { type: string; ts: string; payload: unknown };
        this.lastEventAt = payload.ts;
        if (payload.type === 'market_snapshot' || payload.type === 'market_tick') {
          this.pulse = Array.isArray(payload.payload) ? payload.payload as MarketPulseItem[] : [];
        } else if (payload.type === 'watchlist_quote') {
          this.watchlistQuotes = Array.isArray(payload.payload) ? payload.payload as WatchlistQuote[] : [];
        } else if (payload.type === 'signal_updated' || payload.type === 'signal_created' || payload.type === 'signal_resolved') {
          this.signals = Array.isArray(payload.payload) ? payload.payload as SignalItem[] : this.signals;
        } else if (payload.type === 'diagnostic_updated') {
          this.diagnostics = payload.payload as DiagnosticsOverview;
        } else if (payload.type === 'system_status') {
          const statusPayload = payload.payload as { status?: string; is_trading?: boolean; legacy?: boolean };
          this.systemStatus = statusPayload.status ?? 'unknown';
          this.isTrading = Boolean(statusPayload.is_trading ?? true);
          this.legacyMode = Boolean(statusPayload.legacy ?? false);
        }
      };

      socket.onclose = () => {
        this.connected = false;
        this.connecting = false;
        this.socket = null;
        if (!this.manualClose) {
          const delay = reconnectSteps[Math.min(this.reconnectAttempt, reconnectSteps.length - 1)];
          this.reconnectAttempt += 1;
          window.setTimeout(() => this.connect(), delay);
        }
      };

      socket.onerror = () => {
        this.connected = false;
        this.connecting = false;
      };
    },
    disconnect() {
      this.manualClose = true;
      if (this.socket) {
        this.socket.close();
      }
      this.socket = null;
      this.connected = false;
      this.connecting = false;
    },
  },
});
