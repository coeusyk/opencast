"""Rolling month window helpers — source of truth: config.json max_tracked_months."""

from __future__ import annotations

import json
import os
from datetime import date
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import pandas as pd

_HERE = os.path.dirname(__file__)
_CONFIG_PATH = os.path.join(_HERE, "..", "config.json")


def load_config() -> dict:
    try:
        with open(_CONFIG_PATH, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def max_tracked_months() -> int:
    try:
        return max(1, int(load_config().get("max_tracked_months", 48)))
    except (TypeError, ValueError):
        return 48


def latest_complete_month() -> str:
    """Latest month assumed to have complete Lichess data (previous calendar month)."""
    today = date.today()
    if today.month == 1:
        return f"{today.year - 1:04d}-12"
    return f"{today.year:04d}-{today.month - 1:02d}"


def _shift_month(year: int, month: int, offset: int) -> tuple[int, int]:
    """Shift calendar month by offset (negative = into the past)."""
    total = year * 12 + (month - 1) + offset
    return total // 12, total % 12 + 1


def earliest_tracked_month(latest_month: str, *, window: int | None = None) -> str:
    """First YYYY-MM in an inclusive rolling window ending at latest_month."""
    n = window if window is not None else max_tracked_months()
    y, m = map(int, str(latest_month)[:7].split("-"))
    ey, em = _shift_month(y, m, -(n - 1))
    return f"{ey:04d}-{em:02d}"


def effective_fetch_start(*, latest_month: str | None = None) -> str:
    """Earliest month to fetch: max(config fetch_start, rolling window floor)."""
    cfg = load_config()
    configured = str(cfg.get("fetch_start", "2023-01"))[:7]
    anchor = (latest_month or latest_complete_month())[:7]
    floor = earliest_tracked_month(anchor)
    return max(configured, floor)


def latest_month_str(months) -> str | None:
    """Return the latest YYYY-MM from an iterable of month strings."""
    cleaned = sorted({str(m)[:7] for m in months if m is not None and str(m).strip()})
    return cleaned[-1] if cleaned else None


def filter_dataframe_to_tracked_window(
    df: "pd.DataFrame",
    month_col: str = "month",
    *,
    latest_month: str | None = None,
    window: int | None = None,
) -> "pd.DataFrame":
    """Keep only rows whose month falls in the rolling tracked window."""
    if df.empty or month_col not in df.columns:
        return df
    anchor = latest_month or latest_month_str(df[month_col])
    if not anchor:
        return df
    floor = earliest_tracked_month(anchor, window=window)
    months = df[month_col].astype(str).str[:7]
    return df[months >= floor].copy()
