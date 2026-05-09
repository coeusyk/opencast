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
        If any break exists for the ECO, classification is computed on the
        post-break regime only (last break onward).
        If no break exists, classification uses the last min(12, len(series))
        points to reflect recent regime behavior.
    min_r2:
        Minimum R² required before asserting a non-stable direction.
    """
    _zero = TrendSignal(eco, "stable", 0.0, 0.0, 0, 0.0, "low")

    series_clean = series.dropna().astype(float).reset_index(drop=True)
    if len(series_clean) < 3:
        return _zero

    # Classification window:
    # - with break(s): post-last-break window
    # - without break: most recent 12 months (or fewer if shorter history)
    y_window: np.ndarray
    used_break_window = False
    if structural_breaks is not None and len(structural_breaks) == len(series):
        valid_mask = np.asarray(series.notna().reset_index(drop=True).values, dtype=bool)
        break_values = np.asarray(structural_breaks.reset_index(drop=True).values, dtype=bool)
        breaks_aligned = break_values[valid_mask]
        break_positions = np.where(breaks_aligned)[0]
        if len(break_positions) > 0:
            cut = int(break_positions[-1])
            y_window = series_clean.iloc[cut:].to_numpy(dtype=float)
            used_break_window = True
        else:
            y_window = series_clean.iloc[-min(12, len(series_clean)):].to_numpy(dtype=float)
    else:
        y_window = series_clean.iloc[-min(12, len(series_clean)):].to_numpy(dtype=float)

    if len(y_window) < 3:
        return _zero

    # ── OLS regression ───────────────────────────────────────────────────────
    x = np.arange(len(y_window), dtype=float)
    slope, intercept = np.polyfit(x, y_window, 1)
    y_hat = slope * x + intercept
    ss_res = float(np.sum((y_window - y_hat) ** 2))
    ss_tot = float(np.sum((y_window - np.mean(y_window)) ** 2))
    r_sq = 0.0 if ss_tot <= 0 else float(max(0.0, 1.0 - (ss_res / ss_tot)))
    slope = float(slope)

    # ── Tail-streak counter ──────────────────────────────────────────────────
    # Count consecutive months at the series tail that move in the direction
    # implied by the slope.  Computed over the last 6 month-to-month diffs.
    tail = y_window[-7:] if len(y_window) >= 7 else y_window
    diffs = np.diff(tail)
    dominant = "rising" if slope > 0 else "falling"
    streak = 0
    for d in reversed(diffs):
        if (dominant == "rising" and d > 0) or (dominant == "falling" and d < 0):
            streak += 1
        else:
            break

    recent_slice = y_window[-6:] if len(y_window) >= 6 else y_window
    recent_volatility = float(np.std(recent_slice))
    signal_to_noise = abs(float(slope)) * 6.0 / max(recent_volatility, 1e-9)

    # ── Direction gate ───────────────────────────────────────────────────────
    if abs(slope) < _SLOPE_THRESHOLD or r_sq < min_r2 or (used_break_window and streak < 2):
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
