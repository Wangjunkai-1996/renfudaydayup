from renfu.notifications import NotificationHub


class DummyResponse:
    def raise_for_status(self):
        return None

    def json(self):
        return {'code': 0, 'message': 'success'}


class DummySession:
    def __init__(self):
        self.calls = []

    def post(self, url, data=None, timeout=None):
        self.calls.append({'url': url, 'data': data, 'timeout': timeout})
        return DummyResponse()


def test_notification_hub_sends_signal_message():
    session = DummySession()
    hub = NotificationHub(sendkey='SCTdemo', session=session, async_mode=False)

    ok, msg = hub.send_signal({
        'id': 'sig-1',
        'type': 'BUY',
        'name': '江苏神通',
        'code': 'sz002438',
        'date': '2026-03-07',
        'time': '10:01:02',
        'price': 12.345,
        'bull_score': 0.88,
        'bear_score': 0.12,
        'signal_profile': 'jsst_v1',
        'desc': '量价共振'
    })

    assert ok is True
    assert msg == 'sent'
    assert session.calls[0]['url'].endswith('/SCTdemo.send')
    assert '江苏神通' in session.calls[0]['data']['desp']
    assert '买点提醒' in session.calls[0]['data']['title']


def test_notification_hub_dedupes_same_signal():
    session = DummySession()
    hub = NotificationHub(sendkey='SCTdemo', session=session, async_mode=False, dedupe_sec=600)
    payload = {
        'id': 'sig-dup',
        'type': 'SELL',
        'name': '江苏神通',
        'code': 'sz002438',
        'time': '10:05:00',
        'price': 12.3
    }

    first_ok, _ = hub.send_signal(payload)
    second_ok, second_msg = hub.send_signal(payload)

    assert first_ok is True
    assert second_ok is False
    assert second_msg == 'deduped'
    assert len(session.calls) == 1


def test_notification_hub_sends_risk_pause_message():
    session = DummySession()
    hub = NotificationHub(sendkey='SCTdemo', session=session, async_mode=False)

    ok, msg = hub.send_risk_pause(
        reason='max_consecutive_fail_reached',
        pause_minutes=30,
        paused_until_ts=1772859000,
        context={'code': 'sz002438', 'streak': 2}
    )

    assert ok is True
    assert msg == 'sent'
    assert '风控暂停' in session.calls[0]['data']['title']
    assert '连续失败次数触发风控' in session.calls[0]['data']['desp']
