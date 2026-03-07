import datetime
import os
import threading
import time

import requests


RISK_REASON_LABELS = {
    'max_consecutive_fail_reached': '连续失败次数触发风控',
    'stock_consecutive_fail_reached': '单票连续失败次数触发风控',
    'daily_profit_floor_breached': '当日收益跌破下限',
    'daily_drawdown_limit_breached': '当日回撤超限'
}


def _env_bool(name, default='0'):
    return str(os.getenv(name, default)).strip().lower() in ('1', 'true', 'yes', 'on')


def _clean_text(value, fallback=''):
    text = str(value or '').strip()
    if text:
        return text
    return str(fallback or '').strip()


def _format_price(value):
    try:
        return f'{float(value):.3f}'
    except Exception:
        return _clean_text(value, '-')


class NotificationHub:
    def __init__(
        self,
        *,
        sendkey='',
        api_base='https://sctapi.ftqq.com',
        title_prefix='Renfu',
        enabled=True,
        notify_open=True,
        notify_risk=True,
        timeout_sec=8,
        dedupe_sec=180,
        async_mode=True,
        session=None
    ):
        self.sendkey = _clean_text(sendkey)
        self.api_base = _clean_text(api_base, 'https://sctapi.ftqq.com').rstrip('/')
        self.title_prefix = _clean_text(title_prefix, 'Renfu')
        self.enabled = bool(enabled)
        self.notify_open = bool(notify_open)
        self.notify_risk = bool(notify_risk)
        self.timeout_sec = max(3, int(timeout_sec or 8))
        self.dedupe_sec = max(1, int(dedupe_sec or 180))
        self.async_mode = bool(async_mode)
        self.session = session or requests
        self._recent = {}
        self._lock = threading.Lock()

    @classmethod
    def from_env(cls):
        timeout_sec = 8
        dedupe_sec = 180
        try:
            timeout_sec = max(3, int(os.getenv('SERVERCHAN_TIMEOUT_SEC', '8')))
        except Exception:
            timeout_sec = 8
        try:
            dedupe_sec = max(1, int(os.getenv('SERVERCHAN_DEDUPE_SEC', '180')))
        except Exception:
            dedupe_sec = 180
        return cls(
            sendkey=os.getenv('SERVERCHAN_SENDKEY') or os.getenv('SENDKEY', ''),
            api_base=os.getenv('SERVERCHAN_API_BASE', 'https://sctapi.ftqq.com'),
            title_prefix=os.getenv('SERVERCHAN_TITLE_PREFIX', 'Renfu'),
            enabled=_env_bool('SERVERCHAN_ENABLED', '1'),
            notify_open=_env_bool('SERVERCHAN_NOTIFY_OPEN', '1'),
            notify_risk=_env_bool('SERVERCHAN_NOTIFY_RISK', '1'),
            timeout_sec=timeout_sec,
            dedupe_sec=dedupe_sec,
            async_mode=True
        )

    def is_configured(self):
        return self.enabled and bool(self.sendkey)

    def status_text(self):
        if not self.enabled:
            return 'disabled'
        if not self.sendkey:
            return 'unconfigured'
        return 'serverchan'

    def _remember_once(self, dedupe_key='', ttl_sec=None):
        key = _clean_text(dedupe_key)
        if not key:
            return True

        ttl = max(1, int(ttl_sec or self.dedupe_sec))
        now_ts = time.time()
        with self._lock:
            expired = [k for k, ts in self._recent.items() if now_ts - ts >= ttl]
            for item in expired:
                self._recent.pop(item, None)

            prev_ts = self._recent.get(key)
            if prev_ts is not None and now_ts - prev_ts < ttl:
                return False

            self._recent[key] = now_ts
        return True

    def _post(self, title, body='', short=''):
        if not self.is_configured():
            return False, 'serverchan not configured'

        payload = {
            'title': _clean_text(title, f'{self.title_prefix} 提醒')[:128],
            'desp': _clean_text(body, 'Renfu notification')
        }
        short_text = _clean_text(short)
        if short_text:
            payload['short'] = short_text[:64]

        url = f'{self.api_base}/{self.sendkey}.send'
        try:
            resp = self.session.post(url, data=payload, timeout=(3.05, self.timeout_sec))
            if hasattr(resp, 'raise_for_status'):
                resp.raise_for_status()
            try:
                data = resp.json()
            except Exception:
                data = None
            if isinstance(data, dict):
                code = data.get('code')
                if code not in (None, 0, '0'):
                    message = data.get('message') or data.get('msg') or f'code={code}'
                    raise RuntimeError(str(message))
        except Exception as exc:
            print(f'serverchan notify error: {exc}')
            return False, str(exc)

        return True, 'sent'

    def send_text(self, title, body='', short='', dedupe_key='', dedupe_ttl_sec=None, async_mode=None):
        if not self.is_configured():
            return False, 'serverchan not configured'
        if dedupe_key and not self._remember_once(dedupe_key, ttl_sec=dedupe_ttl_sec):
            return False, 'deduped'

        use_async = self.async_mode if async_mode is None else bool(async_mode)
        if use_async:
            thread = threading.Thread(target=self._post, args=(title, body, short), daemon=True)
            thread.start()
            return True, 'queued'
        return self._post(title, body, short)

    def send_signal(self, signal):
        if not self.notify_open:
            return False, 'disabled'

        sig = dict(signal or {})
        sig_type = _clean_text(sig.get('type'), 'BUY').upper()
        tag = '买点' if sig_type == 'BUY' else '卖点'
        stock_name = _clean_text(sig.get('name'), '未知标的')
        stock_code = _clean_text(sig.get('code'), '-')
        signal_id = _clean_text(sig.get('id'))
        date_str = _clean_text(sig.get('date'), datetime.datetime.now().strftime('%Y-%m-%d'))
        time_str = _clean_text(sig.get('time'), '--:--:--')
        bull_score = _clean_text(sig.get('bull_score'), '-')
        bear_score = _clean_text(sig.get('bear_score'), '-')
        body = '\n'.join([
            f'### {tag}提醒',
            f'- 标的：{stock_name} ({stock_code})',
            f'- 时间：{date_str} {time_str}',
            f'- 价格：{_format_price(sig.get("price"))}',
            f'- 信号：{sig_type}',
            f'- Bull / Bear：{bull_score} / {bear_score}',
            f'- 画像：{_clean_text(sig.get("signal_profile"), "-")}',
            f'- 说明：{_clean_text(sig.get("desc"), "-")}',
            f'- 信号ID：{signal_id or "-"}'
        ])
        short = f'{tag} {stock_name} {_format_price(sig.get("price"))}'
        dedupe_key = f'signal-open:{signal_id or stock_code + ":" + time_str + ":" + sig_type}'
        return self.send_text(
            f'{self.title_prefix} {tag}提醒',
            body,
            short=short,
            dedupe_key=dedupe_key,
            dedupe_ttl_sec=max(180, self.dedupe_sec)
        )

    def send_risk_pause(self, *, reason='', pause_minutes=0, paused_until_ts=0.0, context=None):
        if not self.notify_risk:
            return False, 'disabled'

        context = dict(context or {})
        label = RISK_REASON_LABELS.get(reason, _clean_text(reason, '风控触发'))
        until_text = '-'
        if paused_until_ts:
            until_text = datetime.datetime.fromtimestamp(float(paused_until_ts)).strftime('%Y-%m-%d %H:%M:%S')
        context_text = ', '.join(f'{k}={v}' for k, v in sorted(context.items()) if v not in (None, '', [], {})) or '-'
        body = '\n'.join([
            '### 风控暂停提醒',
            f'- 原因：{label}',
            f'- 暂停分钟：{int(pause_minutes or 0)}',
            f'- 恢复时间：{until_text}',
            f'- 上下文：{context_text}'
        ])
        short = f'风控暂停 {label}'
        dedupe_key = f'risk:{_clean_text(reason)}:{int(float(paused_until_ts or 0.0))}'
        return self.send_text(
            f'{self.title_prefix} 风控暂停',
            body,
            short=short,
            dedupe_key=dedupe_key,
            dedupe_ttl_sec=max(300, self.dedupe_sec)
        )

    def send_test(self, title='', body=''):
        title_text = _clean_text(title, '测试通知')
        if not body:
            body = '\n'.join([
                '### Renfu 测试通知',
                f'- 时间：{datetime.datetime.now().isoformat(timespec="seconds")}',
                '- 说明：如果你在微信里看到这条消息，说明 Server酱 已接通'
            ])
        return self.send_text(f'{self.title_prefix} {title_text}', body, short=title_text, dedupe_key='')
