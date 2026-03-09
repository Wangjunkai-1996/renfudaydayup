import { defineStore } from 'pinia';

export const useRealtimeStore = defineStore('realtime', {
  state: () => ({
    connected: false,
    pulse: [] as Array<{ symbol: string; name: string; last_price: number; change_pct: number }>,
    signals: [] as Array<{ id: string; symbol: string; name: string; side: string; status: string; price: number; occurred_at: string }>,
    systemStatus: 'idle',
    lastEventAt: '' as string,
    socket: null as WebSocket | null,
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
       if (this.socket && (this.socket.readyState === WebSocket.OPEN || this.socket.readyState === WebSocket.CONNECTING)) {
         return;
       }
       const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
       const target = `${protocol}//${window.location.host}/ws/v1/stream`;
       const socket = new WebSocket(target);
       this.socket = socket;

       socket.onopen = () => {
         this.connected = true;
       };

       socket.onmessage = (event) => {
         const payload = JSON.parse(event.data) as { type: string; ts: string; payload: any };
         this.lastEventAt = payload.ts;
         if (payload.type === 'market_snapshot') {
           this.pulse = payload.payload ?? [];
         } else if (payload.type === 'signal_updated') {
           this.signals = payload.payload ?? [];
         } else if (payload.type === 'system_status') {
           this.systemStatus = payload.payload?.status ?? 'unknown';
         }
       };

       socket.onclose = () => {
         this.connected = false;
         this.socket = null;
       };

       socket.onerror = () => {
         this.connected = false;
       };
     },
     disconnect() {
       if (this.socket) {
         this.socket.close();
       }
       this.socket = null;
       this.connected = false;
     },
   },
});
