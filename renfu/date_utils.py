import datetime


def normalize_date_str(date_str, fallback_today=False):
    if not date_str:
        return datetime.datetime.now().strftime('%Y-%m-%d') if fallback_today else None
    try:
        return datetime.datetime.strptime(str(date_str), '%Y-%m-%d').strftime('%Y-%m-%d')
    except Exception:
        return None


def is_valid_iso_date(date_str):
    try:
        datetime.date.fromisoformat(str(date_str))
        return True
    except Exception:
        return False
