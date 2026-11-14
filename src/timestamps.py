"""UTC instants and the Beijing clock used in Chinese digests."""

from datetime import datetime, timezone
from zoneinfo import ZoneInfo


SHANGHAI = ZoneInfo("Asia/Shanghai")


def as_utc(moment: datetime) -> datetime:
    """Return an aware UTC instant.

    A naive value is treated as UTC, matching the RSS parser's fallback.
    """
    if moment.tzinfo is None:
        return moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(timezone.utc)


def within_collection_window(published_at: datetime, since: datetime) -> bool:
    """True when the item is not older than the collection cutoff."""
    return as_utc(published_at) >= as_utc(since)


def shanghai_parts(moment: datetime) -> tuple[int, int, str]:
    """Month, day, and HH:MM on the Asia/Shanghai clock."""
    local = as_utc(moment).astimezone(SHANGHAI)
    return local.month, local.day, f"{local:%H:%M}"
