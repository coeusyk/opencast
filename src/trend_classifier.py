"""OLS-based trend classifier for win-rate time series.

Replaces the fragile single-point diff used by _forecast_directions() with a
full linear regression over the actual win-rate history, gated by R² and a
tail-streak counter so transient spikes don't produce false trend signals.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy import stats


# Per-month slope magnitude below which the series is called "stable".
# 0.0003 ≈ 0.03 percentage-points per month — below typical monthly noise.
_SLOPE_THRESHOLD: float = 0.0003

# Minimum R² for the regression to be called meaningful.
_DEFAULT_MIN_R2: float = 0.15


@dataclass
class TrendSignal:
    eco: str
    direction: str           # "rising" | "falling" | "stable"
    slope_per_month: float   # raw OLS slope on win-rate (units: win-rate / month)
    r_squared: float         # goodness of fit — low R² = noisy series
    sustained_months: int    # consecutive tail months in the dominant direction
    recent_volatility: float # std dev of the last 6 months of win-rate
    confidence: str          # "high" | "medium" | "low"


def classify_trend(
    eco: str,
    series: pd.Series,
    structural_breaks: pd.Series | None = None,
    min_r2: float = _DEFAULT_MIN_R2,
) -> TrendSignal:
    """Return a TrendSignal for a win-rate time series.

    Parameters
    ----------
    eco:
        ECO code (used only to label the returned dataclass).
    series:
        Pandas Series of white win-rate values, ordered oldest-to-newest.
        Index is ignored; position is used as the time axis.
    structural_breaks:
        Optional boolean Series aligned to *series* (same length, same order).
        Present for interface compatibility with callers that also surface
        structural-break information separately. Trend classification itself is
        computed over the full available series.
    min_r2:
        Minimum R² required before asserting a non-stable direction.
    """
    _zero = TrendSignal(eco, "stable", 0.0, 0.0, 0, 0.0, "low")

    y = series.dropna().values.astype(float)
    if len(y) < 6:
        return _zero

    # ── OLS regression ───────────────────────────────────────────────────────
    x = np.arange(len(y), dtype=float)
    slope, _, r_value, _, _ = stats.linregress(x, y)
    r_sq = float(r_value ** 2)

    # ── Tail-streak counter ──────────────────────────────────────────────────
    # Count consecutive months at the series tail that move in the direction
    # implied by the slope.  Computed over the last 6 month-to-month diffs.
    tail = y[-7:]  # need 7 points to get 6 diffs
    diffs = np.diff(tail)
    dominant = "rising" if slope > 0 else "falling"
    streak = 0
    for d in reversed(diffs):
        if (dominant == "rising" and d > 0) or (dominant == "falling" and d < 0):
            streak += 1
        else:
            break

    recent_volatility = float(np.std(y[-6:]))
    signal_to_noise = abs(float(slope)) * 6.0 / max(recent_volatility, 1e-9)

    # ── Direction gate ───────────────────────────────────────────────────────
    if abs(slope) < _SLOPE_THRESHOLD or r_sq < min_r2:
        direction = "stable"
    else:
        direction = dominant

    # ── Confidence ───────────────────────────────────────────────────────────
    if direction == "stable":
        confidence = "low"
    elif r_sq >= 0.50 and streak >= 2 and signal_to_noise >= 2.0:
        confidence = "high"
    elif r_sq >= min_r2 and streak >= 1:
        confidence = "medium"
    else:
        confidence = "low"

    return TrendSignal(
        eco=eco,
        direction=direction,
        slope_per_month=float(slope),
        r_squared=r_sq,
        sustained_months=streak if direction != "stable" else 0,
        recent_volatility=recent_volatility,
        confidence=confidence,
    )
