import datetime
import threading
import time


class TradeCalendar:
    def __init__(self, ak_module=None, refresh_sec=6 * 60 * 60):
        self._ak = ak_module
        self._refresh_sec = max(60, int(refresh_sec or 0))
        self._lock = threading.RLock()
        self._loaded_at_ts = 0.0
        self._days = set()
        self._source = 'weekday_fallback'

    @property
    def source(self):
        with self._lock:
            return self._source

    @staticmethod
    def normalize_trade_day(value):
        if value is None:
            return ''
        if isinstance(value, datetime.datetime):
            return value.strftime('%Y-%m-%d')
        if isinstance(value, datetime.date):
            return value.strftime('%Y-%m-%d')
        text = str(value).strip()
        if not text:
            return ''
        text = text[:10]
        try:
            return datetime.datetime.strptime(text, '%Y-%m-%d').strftime('%Y-%m-%d')
        except Exception:
            return ''

    def refresh(self, force=False):
        now_ts = time.time()
        with self._lock:
            loaded_at_ts = float(self._loaded_at_ts)
        if (not force) and loaded_at_ts > 0 and (now_ts - loaded_at_ts) < self._refresh_sec:
            return

        days = set()
        source = 'weekday_fallback'
        if self._ak is not None:
            try:
                df = self._ak.tool_trade_date_hist_sina()
                if df is not None and 'trade_date' in df.columns:
                    days = {self.normalize_trade_day(v) for v in df['trade_date'].tolist()}
                    days = {d for d in days if d}
                    if days:
                        source = 'akshare_sina'
            except Exception:
                pass

        with self._lock:
            if days:
                self._days = days
                self._source = source
            self._loaded_at_ts = now_ts

    def is_trade_day(self, dt=None):
        dt = dt or datetime.datetime.now()
        if isinstance(dt, datetime.date) and not isinstance(dt, datetime.datetime):
            dt = datetime.datetime.combine(dt, datetime.time(hour=12))
        if dt.weekday() >= 5:
            return False
        self.refresh()
        with self._lock:
            cal_days = set(self._days)
        if cal_days:
            return dt.strftime('%Y-%m-%d') in cal_days
        return dt.weekday() < 5

