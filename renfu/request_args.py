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
