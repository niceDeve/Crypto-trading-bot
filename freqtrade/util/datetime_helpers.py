from datetime import datetime, timezone


def dt_now() -> datetime:
    """Return the current datetime in UTC."""
    return datetime.now(timezone.utc)


def dt_from_ts(timestamp: float) -> datetime:
    """
    Return a datetime from a timestamp.
    :param timestamp: timestamp in seconds or milliseconds
    """
    if timestamp > 1e10:
        # Timezone in ms - convert to seconds
        timestamp /= 1000
    return datetime.fromtimestamp(timestamp, tz=timezone.utc)
