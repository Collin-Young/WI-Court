"""Utility helpers for WI scraper."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Generator, Optional, Tuple


def parse_date(value: str | None) -> Optional[date]:
    """Parse API date formats into ``date`` objects."""
    if not value:
        return None

    parts = value.split("-")
    if len(parts) == 3:
        year, month, day = (int(part) for part in parts)
        return date(year, month, day)
    if len(parts) == 2:
        year, month = (int(part) for part in parts)
        return date(year, month, 1)
    raise ValueError(f"Unrecognized date format: {value}")


def iter_windows(start: date, end: date, span_days: int = 7) -> Generator[Tuple[date, date], None, None]:
    """Yield inclusive windows covering start..end using ``span_days`` buckets."""
    if span_days < 1:
        raise ValueError("span_days must be >= 1")

    current = start
    delta = timedelta(days=span_days - 1)
    one_day = timedelta(days=1)

    while current <= end:
        window_end = min(current + delta, end)
        yield current, window_end
        current = window_end + one_day


__all__ = ["parse_date", "iter_windows"]
