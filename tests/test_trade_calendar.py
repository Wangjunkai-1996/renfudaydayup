import datetime

from renfu.trade_calendar import TradeCalendar


class _Series(list):
    def tolist(self):
        return list(self)


class _Frame:
    columns = ['trade_date']

    def __getitem__(self, key):
        if key != 'trade_date':
            raise KeyError(key)
        return _Series(['2026-03-02', '2026-03-03'])


class _FakeAk:
    def tool_trade_date_hist_sina(self):
        return _Frame()


def test_trade_calendar_weekday_fallback():
    calendar = TradeCalendar(ak_module=None)
    assert calendar.is_trade_day(datetime.date(2026, 3, 7)) is False  # Saturday
    assert calendar.is_trade_day(datetime.date(2026, 3, 9)) is True   # Monday


def test_trade_calendar_uses_akshare_when_available():
    calendar = TradeCalendar(ak_module=_FakeAk(), refresh_sec=10)
    assert calendar.is_trade_day(datetime.date(2026, 3, 2)) is True
    assert calendar.is_trade_day(datetime.date(2026, 3, 4)) is False
    assert calendar.source == 'akshare_sina'

