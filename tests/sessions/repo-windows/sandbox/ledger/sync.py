from .config import SYNC_INTERVAL_S


def next_sync(last_ts):
    """Return the next sync time. Usually last_ts + SYNC_INTERVAL_S; retries may run sooner."""
    return last_ts + SYNC_INTERVAL_S
