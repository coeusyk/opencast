import logging
import os
import time
import warnings

import numpy as np
import pandas as pd
import statsmodels.api as sm
from scipy import stats
from statsmodels.tsa.stattools import adfuller
from statsmodels.stats.diagnostic import acorr_ljungbox
from statsmodels.tsa.holtwinters import ExponentialSmoothing

import pmdarima as pm

warnings.filterwarnings("ignore")

_HERE = os.path.dirname(__file__)
PROCESSED_CSV = os.path.join(_HERE, "..", "data", "processed", "openings_ts.csv")
CATALOG_CSV   = os.path.join(_HERE, "..", "data", "openings_catalog.csv")
OUTPUT_CSV    = os.path.join(_HERE, "..", "data", "output", "forecasts.csv")

MIN_POINTS = 24
FORECAST_STEPS = 3
OUTPUT_COLUMNS = [
    "eco",
    "opening_name",
    "month",
    "actual",
    "forecast",
    "lower_ci",
    "upper_ci",
    "is_forecast",
    "structural_break",
    "model_tier",
]

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
log = logging.getLogger(__name__)

ECO_TIMING_WARN_S = 60.0  # warn if a single ECO takes longer than this


def _chow_test(y: np.ndarray, bp: int) -> tuple:
    """Chow structural break test at index bp. Returns (F-stat, p-value)."""
    n = len(y)
    t = np.arange(n, dtype=float)
    X = sm.add_constant(t)
    rss_full = sm.OLS(y, X).fit().ssr

    if bp < 6 or (n - bp) < 6:
        return 0.0, 1.0

    rss_before = sm.OLS(y[:bp], sm.add_constant(t[:bp])).fit().ssr
    rss_after  = sm.OLS(y[bp:], sm.add_constant(t[bp:])).fit().ssr

    k = 2  # intercept + slope
    denom = rss_before + rss_after
    if denom == 0:
        return 0.0, 1.0

    F = ((rss_full - denom) / k) / (denom / (n - 2 * k))
    p = float(1 - stats.f.cdf(F, k, n - 2 * k))
    return float(F), p


def _detect_breaks(y: np.ndarray, months: list, alpha: float = 0.05) -> set:
    """Return set of Timestamps where a Chow structural break is detected."""
    breaks = set()
    for bp in range(6, len(y) - 6):
        _, p = _chow_test(y, bp)
        if p < alpha:
            breaks.add(months[bp])
    return breaks


def run_timeseries(df: pd.DataFrame | None = None) -> pd.DataFrame:
    if df is None:
        df = pd.read_csv(PROCESSED_CSV)
    else:
        df = df.copy()

    # Load catalog and split into tiers
    catalog = pd.read_csv(CATALOG_CSV)
    tier1_ecos = set(catalog.loc[catalog["model_tier"] == 1, "eco"])
    tier2_ecos = set(catalog.loc[catalog["model_tier"] == 2, "eco"])
    tier3_ecos = set(catalog.loc[catalog["model_tier"] == 3, "eco"])
    log.info("Timeseries: processing %d Tier-1 ECOs", len(tier1_ecos))

    df["month"] = pd.to_datetime(df["month"])
    os.makedirs(os.path.dirname(OUTPUT_CSV), exist_ok=True)

    records = []
    tier1_times: list[float] = []
    tier2_times: list[float] = []

    # ── Tier 1: ARIMA + Chow + Ljung-Box ─────────────────────────────────────
    tier1_df = df[df["eco"].isin(tier1_ecos)]
    for eco, grp in tier1_df.groupby("eco"):
        t0 = time.perf_counter()
        grp = grp.sort_values("month").reset_index(drop=True)
        opening_name = grp["opening_name"].iloc[0]
        n = len(grp)

        if n < MIN_POINTS:
            log.warning("%s: only %d data points, need \u2265 %d \u2014 skipping", eco, n, MIN_POINTS)
            continue

        y = np.asarray(grp["white_win_rate"].values, dtype=float)
        months = grp["month"].tolist()

        # ADF test: first-difference if non-stationary
        adf_pvalue = adfuller(y, autolag="AIC")[1]
        d = 1 if adf_pvalue > 0.05 else 0

        # Fit ARIMA via AIC-guided search
        model = pm.auto_arima(
            y,
            d=d,
            start_p=0, max_p=3,
            start_q=0, max_q=3,
            information_criterion="aic",
            stepwise=True,
            suppress_warnings=True,
            error_action="ignore",
        )

        # Ljung-Box on residuals
        lb_p = acorr_ljungbox(model.resid(), lags=[10], return_df=True)["lb_pvalue"].iloc[0]
        if lb_p < 0.05:
            log.warning("%s ARIMA%s: residual autocorrelation (Ljung-Box p=%.3f)", eco, model.order, lb_p)
        else:
            log.info("%s ARIMA%s: OK (Ljung-Box p=%.3f)", eco, model.order, lb_p)

        # Structural breaks
        break_months = _detect_breaks(y, months)

        # Forecast
        forecast_vals, conf_int = model.predict(
            n_periods=FORECAST_STEPS, return_conf_int=True, alpha=0.05
        )
        last_month = months[-1]
        future_months = pd.date_range(start=last_month, periods=FORECAST_STEPS + 1, freq="MS")[1:]

        # Historical rows
        for _, row in grp.iterrows():
            records.append({
                "eco": eco,
                "opening_name": opening_name,
                "month": row["month"].strftime("%Y-%m"),
                "actual": row["white_win_rate"],
                "forecast": None,
                "lower_ci": None,
                "upper_ci": None,
                "is_forecast": False,
                "structural_break": row["month"] in break_months,
                "model_tier": 1,
            })

        # Forecast rows
        for fm, fc, ci in zip(future_months, forecast_vals, conf_int):
            records.append({
                "eco": eco,
                "opening_name": opening_name,
                "month": fm.strftime("%Y-%m"),
                "actual": None,
                "forecast": round(float(fc), 6),
                "lower_ci": round(float(ci[0]), 6),
                "upper_ci": round(float(ci[1]), 6),
                "is_forecast": True,
                "structural_break": False,
                "model_tier": 1,
            })

        elapsed = time.perf_counter() - t0
        tier1_times.append(elapsed)
        if elapsed > ECO_TIMING_WARN_S:
            log.warning("%s (Tier 1): took %.1fs, exceeds %.0fs budget", eco, elapsed, ECO_TIMING_WARN_S)

    # ── Tier 2: Holt-Winters (additive trend, no seasonality) ────────────────
    tier2_df = df[df["eco"].isin(tier2_ecos)]
    for eco, grp in tier2_df.groupby("eco"):
        t0 = time.perf_counter()
        grp = grp.sort_values("month").reset_index(drop=True)
        opening_name = grp["opening_name"].iloc[0]

        y = np.asarray(grp["white_win_rate"].values, dtype=float)
        months = grp["month"].tolist()

        if len(y) < 6:  # need at least 6 points for HW with additive trend
            log.warning("%s (Tier 2): only %d data points, skipping", eco, len(y))
            continue

        hw_fit = ExponentialSmoothing(y, trend="add", seasonal=None).fit()
        hw_forecast = hw_fit.forecast(FORECAST_STEPS)
        residual_std = float(np.std(hw_fit.resid, ddof=1))
        half_ci = 1.96 * residual_std

        last_month = months[-1]
        future_months = pd.date_range(start=last_month, periods=FORECAST_STEPS + 1, freq="MS")[1:]

        # Historical rows
        for _, row in grp.iterrows():
            records.append({
                "eco": eco,
                "opening_name": opening_name,
                "month": row["month"].strftime("%Y-%m"),
                "actual": row["white_win_rate"],
                "forecast": None,
                "lower_ci": None,
                "upper_ci": None,
                "is_forecast": False,
                "structural_break": False,
                "model_tier": 2,
            })

        # Forecast rows
        for fm, fc in zip(future_months, hw_forecast):
            records.append({
                "eco": eco,
                "opening_name": opening_name,
                "month": fm.strftime("%Y-%m"),
                "actual": None,
                "forecast": round(float(fc), 6),
                "lower_ci": round(float(fc) - half_ci, 6),
                "upper_ci": round(float(fc) + half_ci, 6),
                "is_forecast": True,
                "structural_break": False,
                "model_tier": 2,
            })

        elapsed = time.perf_counter() - t0
        tier2_times.append(elapsed)
        if elapsed > ECO_TIMING_WARN_S:
            log.warning("%s (Tier 2): took %.1fs, exceeds %.0fs budget", eco, elapsed, ECO_TIMING_WARN_S)

    # ── Tier 3: descriptive stats only, no rows written ───────────────────────
    log.info("Timeseries: skipping %d Tier-3 ECOs (descriptive stats only)", len(tier3_ecos))

    # ── Summary log ───────────────────────────────────────────────────────────
    total_s = sum(tier1_times) + sum(tier2_times)
    t1_avg = sum(tier1_times) / len(tier1_times) if tier1_times else 0.0
    t2_avg = sum(tier2_times) / len(tier2_times) if tier2_times else 0.0
    log.info(
        "Timeseries: %d openings processed in %.1fs (Tier1: %.1fs avg, Tier2: %.1fs avg)",
        len(tier1_times) + len(tier2_times),
        total_s,
        t1_avg,
        t2_avg,
    )

    out = pd.DataFrame(records, columns=OUTPUT_COLUMNS)
    out.to_csv(OUTPUT_CSV, index=False)
    print(f"Forecasts written \u2192 {OUTPUT_CSV}  ({len(out)} rows)")
    return out


if __name__ == "__main__":
    run_timeseries()
