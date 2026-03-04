def parse_int_value(raw, default, *, min_value=None, max_value=None):
    try:
        value = int(raw)
    except Exception:
        value = default

    if min_value is not None:
        value = max(min_value, value)
    if max_value is not None:
        value = min(max_value, value)
    return value


def parse_since_ts_arg(raw):
    text = str(raw or '').strip()
    if not text:
        return None
    try:
        value = float(text)
        if value <= 0:
            return None
        # Accept both seconds and milliseconds.
        return value / 1000.0 if value > 10_000_000_000 else value
    except Exception:
        return None
