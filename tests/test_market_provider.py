from renfu.market_provider import MarketQuoteManager


class _Resp:
    def __init__(self, status_code=200, text='', payload=None):
        self.status_code = status_code
        self.text = text
        self._payload = payload or {}

    def json(self):
        return self._payload


def test_market_provider_fallback_to_eastmoney(monkeypatch):
    def fake_get(url, **kwargs):
        if 'hq.sinajs.cn' in url:
            raise RuntimeError('sina unavailable')
        if 'push2.eastmoney.com' in url:
            return _Resp(
                status_code=200,
                payload={
                    'data': {
                        'f43': 1012,
                        'f44': 1020,
                        'f45': 1000,
                        'f46': 1005,
                        'f47': 200000,
                        'f48': 201000000,
                        'f58': '测试股',
                        'f60': 998
                    }
                }
            )
        raise AssertionError(f'unexpected url: {url}')

    monkeypatch.setattr('renfu.market_provider.requests.get', fake_get)
    manager = MarketQuoteManager()
    result = manager.fetch_quotes(['sh600079'])

    assert result['provider'] == 'eastmoney_push2'
    parts = result['quotes']['sh600079']
    assert len(parts) == 32
    assert float(parts[3]) > 0

