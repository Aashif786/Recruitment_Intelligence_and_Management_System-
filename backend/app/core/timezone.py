from datetime import datetime, timezone, timedelta

IST = timezone(timedelta(hours=5, minutes=30))

def get_ist_now():
    """Returns current time in Indian Standard Time (IST) as a naive datetime object for DB storage."""
    return datetime.now(IST).replace(tzinfo=None)

def to_naive_ist(dt: datetime):
    """Converts a datetime to a naive IST datetime for safe comparison with get_ist_now()."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt
    return dt.astimezone(IST).replace(tzinfo=None)
