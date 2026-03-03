import datetime
import threading
import time

import requests


class MarketQuoteManager:
    """
    行情源容灾：
    - primary: 新浪 hq
    - fallback: 东财 push2
    """
    def __init__(self, headers=None, timeout=5):
        self._headers = headers or {}
        self._timeout = timeout
        self._lock = threading.RLock()
        self._active_provider = 'sina_hq'
        self._fail_count = 0
        self._last_switch_ts = 0.0
        self._last_error = ''

    @staticmethod
    def _to_secid(code):
        text = str(code or '').strip().lower()
        if text.startswith('sh'):
            return f'1.{text[2:]}'
        if text.startswith('sz'):
            return f'0.{text[2:]}'
        return ''

    @staticmethod
    def _safe_float(v, default=0.0):
        try:
            return float(v)
        except Exception:
            return float(default)

    @staticmethod
    def _safe_int(v, default=0):
        try:
            return int(float(v))
        except Exception:
            return int(default)

    def snapshot(self):
        with self._lock:
            return {
                'active_provider': self._active_provider,
                'fail_count': int(self._fail_count),
                'last_switch_ts': float(self._last_switch_ts),
                'last_error': str(self._last_error or '')
            }

    def _switch_provider(self, provider, err_msg=''):
        with self._lock:
            if self._active_provider != provider:
                self._active_provider = provider
                self._last_switch_ts = time.time()
            self._last_error = str(err_msg or '')

    def _mark_success(self, provider):
        with self._lock:
            self._active_provider = provider
            self._fail_count = 0
            self._last_error = ''

    def _mark_failure(self, err_msg):
        with self._lock:
            self._fail_count = int(self._fail_count) + 1
            self._last_error = str(err_msg or '')

    def _fetch_sina(self, codes):
        code_str = ",".join(codes)
        url = f"http://hq.sinajs.cn/list={code_str}"
        response = requests.get(url, headers=self._headers, timeout=self._timeout)
        if response.status_code != 200:
            raise RuntimeError(f"sina status={response.status_code}")

        out = {}
        for line in response.text.strip().split('\n'):
            if not line or '=";' in line:
                continue
            parts_eq = line.split('=')
            if len(parts_eq) < 2:
                continue
            code = parts_eq[0].split('_')[-1].strip().lower()
            content = parts_eq[1].replace('"', '').replace(';', '').strip()
            if not content:
                continue
            parts = content.split(',')
            if len(parts) < 32:
                continue
            out[code] = parts
        if not out:
            raise RuntimeError('sina empty quote payload')
        return out

    def _fetch_eastmoney(self, codes):
        out = {}
        now = datetime.datetime.now()
        date_text = now.strftime('%Y-%m-%d')
        time_text = now.strftime('%H:%M:%S')

        for code in codes:
            secid = self._to_secid(code)
            if not secid:
                continue
            url = (
                "https://push2.eastmoney.com/api/qt/stock/get"
                f"?secid={secid}"
                "&fields=f43,f44,f45,f46,f47,f48,f57,f58,f60"
            )
            response = requests.get(url, timeout=self._timeout)
            if response.status_code != 200:
                raise RuntimeError(f"eastmoney status={response.status_code} code={code}")
            payload = response.json() or {}
            data = payload.get('data') or {}
            if not data:
                raise RuntimeError(f"eastmoney empty data code={code}")

            # 东财价格字段单位通常是 0.01 元。
            cur = self._safe_float(data.get('f43')) / 100.0
            high = self._safe_float(data.get('f44')) / 100.0
            low = self._safe_float(data.get('f45')) / 100.0
            open_p = self._safe_float(data.get('f46')) / 100.0
            volume = self._safe_int(data.get('f47'))
            amount = self._safe_float(data.get('f48'))
            pre_close = self._safe_float(data.get('f60')) / 100.0
            name = str(data.get('f58') or code)
            if cur <= 0:
                continue

            parts = ['0'] * 32
            parts[0] = name
            parts[1] = f"{open_p:.4f}"
            parts[2] = f"{pre_close:.4f}"
            parts[3] = f"{cur:.4f}"
            parts[4] = f"{high:.4f}"
            parts[5] = f"{low:.4f}"
            parts[8] = str(volume)
            parts[9] = f"{amount:.2f}"
            parts[30] = date_text
            parts[31] = time_text
            out[code] = parts

        if not out:
            raise RuntimeError('eastmoney empty quote payload')
        return out

    def fetch_quotes(self, codes):
        code_list = [str(c or '').strip().lower() for c in list(codes or []) if str(c or '').strip()]
        if not code_list:
            return {'provider': self.snapshot()['active_provider'], 'quotes': {}}

        with self._lock:
            active = self._active_provider
            last_switch_ts = float(self._last_switch_ts or 0.0)

        sequence = [active]
        # fallback 运行一段时间后，优先探测主源是否恢复
        if active != 'sina_hq' and (time.time() - last_switch_ts) >= 60:
            sequence = ['sina_hq', active]
        for provider in ('sina_hq', 'eastmoney_push2'):
            if provider not in sequence:
                sequence.append(provider)

        errors = []
        for provider in sequence:
            try:
                if provider == 'sina_hq':
                    quotes = self._fetch_sina(code_list)
                elif provider == 'eastmoney_push2':
                    quotes = self._fetch_eastmoney(code_list)
                else:
                    continue
                self._mark_success(provider)
                return {'provider': provider, 'quotes': quotes}
            except Exception as e:
                err = f'{provider}: {e}'
                errors.append(err)
                self._mark_failure(err)
                # 切换活跃源到下一个，避免下一轮还先打失败源。
                self._switch_provider('eastmoney_push2' if provider == 'sina_hq' else 'sina_hq', err_msg=err)

        raise RuntimeError(' | '.join(errors) if errors else 'all providers failed')
