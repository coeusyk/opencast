import json
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
LONG_TAIL_CSV = os.path.join(_HERE, "..", "data", "output", "long_tail_stats.csv")
MODEL_CHOICE_JSON = os.path.join(_HERE, "..", "data", "output", "model_choice.json")
INTERVAL_CALIBRATION_JSON = os.path.join(_HERE, "..", "data", "output", "interval_calibration.json")

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
    "forecast_quality",
    "model_tier_override",
    "model_name",
]

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
log = logging.getLogger(__name__)

ECO_TIMING_WARN_S = 60.0  # warn if a single ECO takes longer than this
MAX_TIER1_OPENINGS = 300  # soft cap — logs a warning when exceeded
HARD_CAP_TIER1 = 300      # hard cap — covers all data-bearing ECOs


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


def _run_descriptive_stats(eco: str, grp: pd.DataFrame) -> dict:
    """Compute descriptive stats for a Tier-3 opening."""
    y = np.asarray(grp["white_win_rate"].values, dtype=float)
    months = grp["month"].tolist()

    last_month = str(months[-1])[:7]
    last_win_rate  = float(y[-1])
    mean_win_rate  = float(np.mean(y))
    std_win_rate   = float(np.std(y, ddof=1)) if len(y) > 1 else 0.0

    ma3_series = pd.Series(y).rolling(3, min_periods=1).mean().values
    ma3 = float(ma3_series[-1])

    if len(ma3_series) >= 4:
        diff = float(ma3_series[-1]) - float(ma3_series[-4])
        if diff > 0.005:
            trend_direction = "up"
        elif diff < -0.005:
            trend_direction = "down"
        else:
            trend_direction = "flat"
    else:
        trend_direction = "flat"

    eco_group = eco[0] if eco else ""
    opening_name = str(grp["opening_name"].iloc[0]) if "opening_name" in grp.columns else eco

    return {
        "eco": eco,
        "opening_name": opening_name,
        "eco_group": eco_group,
        "model_tier": 3,
        "last_month": last_month,
        "last_win_rate": round(last_win_rate, 6),
        "mean_win_rate": round(mean_win_rate, 6),
        "std_win_rate": round(std_win_rate, 6),
        "ma3": round(ma3, 6),
        "trend_direction": trend_direction,
        "months_available": len(y),
    }


def _forecast_holt_winters(y: np.ndarray, steps: int) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Return Holt-Winters forecast and symmetric 95% CI bounds."""
    hw_fit = ExponentialSmoothing(y, trend="add", seasonal=None).fit()
    hw_forecast = np.asarray(hw_fit.forecast(steps), dtype=float)

    resid = np.asarray(hw_fit.resid, dtype=float)
    if len(resid) > 1:
        residual_std = float(np.std(resid, ddof=1))
    else:
        residual_std = 0.0
    half_ci = 1.96 * residual_std

    lower = hw_forecast - half_ci
    upper = hw_forecast + half_ci
    return hw_forecast, lower, upper


def _forecast_mean_model(y: np.ndarray, steps: int) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Return mean forecast with 95% CI bounds using residual std."""
    mean_val = np.mean(y)
    forecast = np.full(steps, mean_val)

    # Use residual std around mean as CI
    resid = y - mean_val
    if len(resid) > 1:
        residual_std = float(np.std(resid, ddof=1))
    else:
        residual_std = 0.0
    half_ci = 1.96 * residual_std

    lower = forecast - half_ci
    upper = forecast + half_ci
    return forecast, lower, upper


def _forecast_naive_model(y: np.ndarray, steps: int) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Return naive (last-value) forecast with 95% CI bounds."""
    last_val = y[-1]
    forecast = np.full(steps, last_val)

    # Use entire series std as CI
    if len(y) > 1:
        residual_std = float(np.std(y, ddof=1))
    else:
        residual_std = 0.0
    half_ci = 1.96 * residual_std

    lower = forecast - half_ci
    upper = forecast + half_ci
    return forecast, lower, upper


def _load_model_choice() -> tuple[dict[str, dict], dict[str, dict]]:
    """Load offline model-choice and interval calibration artifacts when present."""
    model_choice: dict[str, dict] = {}
    interval_calibration: dict[str, dict] = {}

    if os.path.exists(MODEL_CHOICE_JSON):
        with open(MODEL_CHOICE_JSON, encoding="utf-8") as f:
            model_choice = json.load(f)
        log.info("Loaded model choice for %d ECOs", len(model_choice))
    else:
        log.warning("Model choice missing at %s; using tier defaults", MODEL_CHOICE_JSON)

    if os.path.exists(INTERVAL_CALIBRATION_JSON):
        with open(INTERVAL_CALIBRATION_JSON, encoding="utf-8") as f:
            interval_calibration = json.load(f)
        log.info("Loaded interval calibration for %d models", len(interval_calibration))
    else:
        log.warning("Interval calibration missing at %s; using uncalibrated intervals", INTERVAL_CALIBRATION_JSON)

    return model_choice, interval_calibration


def _apply_interval_calibration(
    model_name: str,
    forecast_vals: np.ndarray,
    conf_int: np.ndarray,
    interval_calibration: dict[str, dict],
) -> np.ndarray:
    """Scale interval width per model and horizon using offline empirical coverage."""
    if model_name not in interval_calibration:
        return conf_int

    adjusted = conf_int.copy()
    for index in range(len(forecast_vals)):
        horizon_key = str(index + 1)
        scale = float(interval_calibration.get(model_name, {}).get(horizon_key, 1.0))
        center = float(forecast_vals[index])
        lower_width = center - float(conf_int[index, 0])
        upper_width = float(conf_int[index, 1]) - center
        adjusted[index, 0] = center - lower_width * scale
        adjusted[index, 1] = center + upper_width * scale
    return adjusted


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

    model_choice, interval_calibration = _load_model_choice()

    n_tier1 = len(tier1_ecos)
    if n_tier1 > HARD_CAP_TIER1:
        # Sort by total game volume descending so the most popular ECOs are kept.
        eco_volumes = (
            df[df["eco"].isin(tier1_ecos)]
            .groupby("eco")["total"]
            .sum()
            .sort_values(ascending=False)
        )
        tier1_ecos = set(eco_volumes.index[:HARD_CAP_TIER1])
        log.warning(
            "Tier-1 ECO count %d exceeds hard cap %d — keeping top %d by game volume",
            n_tier1, HARD_CAP_TIER1, HARD_CAP_TIER1,
        )
    elif n_tier1 > MAX_TIER1_OPENINGS:
        log.warning(
            "Tier-1 ECO count %d exceeds MAX_TIER1_OPENINGS=%d", n_tier1, MAX_TIER1_OPENINGS
        )

    log.info("Timeseries: processing %d Tier-1 ECOs", len(tier1_ecos))

    df["month"] = pd.to_datetime(df["month"])
    os.makedirs(os.path.dirname(OUTPUT_CSV), exist_ok=True)

    records = []
    tier1_times: list[float] = []
    tier2_times: list[float] = []

    # ── Tier 1: Model selection from recommendations or ARIMA default ────────
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

        # Determine which model to use: recommendation or default
        eco_key = str(eco)
        choice = model_choice.get(eco_key, {})
        recommended_model = str(choice.get("model", "arima"))
        model_name_used = recommended_model
        forecast_quality = str(choice.get("confidence", "medium"))
        model_tier_override = ""

        if recommended_model == "mean":
            # Use mean model.
            try:
                forecast_vals, lower_ci, upper_ci = _forecast_mean_model(y, FORECAST_STEPS)
                conf_int = np.column_stack((lower_ci, upper_ci))
                log.info("%s (Tier 1): using mean model from model choice", eco)
            except Exception as exc:
                log.warning("%s (Tier 1): mean model failed (%s), falling back to ARIMA", eco, exc)
                model_name_used = "arima"
        elif recommended_model == "holt_winters":
            try:
                hw_forecast, hw_lower, hw_upper = _forecast_holt_winters(y, FORECAST_STEPS)
                forecast_vals = hw_forecast
                conf_int = np.column_stack((hw_lower, hw_upper))
                log.info("%s (Tier 1): using Holt-Winters model from model choice", eco)
            except Exception as exc:
                log.warning("%s (Tier 1): Holt-Winters failed (%s), falling back to ARIMA", eco, exc)
                model_name_used = "arima"
        elif recommended_model == "naive":
            try:
                forecast_vals, lower_ci, upper_ci = _forecast_naive_model(y, FORECAST_STEPS)
                conf_int = np.column_stack((lower_ci, upper_ci))
                log.info("%s (Tier 1): using naive model from model choice", eco)
            except Exception as exc:
                log.warning("%s (Tier 1): naive model failed (%s), falling back to ARIMA", eco, exc)
                model_name_used = "arima"
        else:
            model_name_used = "arima"

        if model_name_used == "arima":
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

            # Ljung-Box on residuals + misspecification fallback chain
            fitted_order = tuple(model.order)
            lb_p = float(acorr_ljungbox(model.resid(), lags=[10], return_df=True)["lb_pvalue"].iloc[0])

            if lb_p < 0.05 and fitted_order == (0, 0, 0):
                log.warning(
                    "%s ARIMA%s: residual autocorrelation (Ljung-Box p=%.3f), falling back to Holt-Winters",
                    eco,
                    fitted_order,
                    lb_p,
                )
                forecast_quality = "low"
                model_tier_override = "tier1_hw_fallback"
                model_name_used = "holt_winters"
                try:
                    hw_forecast, hw_lower, hw_upper = _forecast_holt_winters(y, FORECAST_STEPS)
                    forecast_vals = hw_forecast
                    conf_int = np.column_stack((hw_lower, hw_upper))
                except Exception as exc:
                    log.warning("%s: Holt-Winters fallback failed (%s), using ARIMA output", eco, exc)
                    model_name_used = "arima"
                    forecast_vals, conf_int = model.predict(
                        n_periods=FORECAST_STEPS, return_conf_int=True, alpha=0.05
                    )
            elif lb_p < 0.05:
                log.warning(
                    "%s ARIMA%s: residual autocorrelation (Ljung-Box p=%.3f), keeping ARIMA but marking forecast_quality=low",
                    eco,
                    fitted_order,
                    lb_p,
                )
                forecast_quality = "low"
                forecast_vals, conf_int = model.predict(
                    n_periods=FORECAST_STEPS, return_conf_int=True, alpha=0.05
                )
            else:
                log.info("%s ARIMA%s: OK (Ljung-Box p=%.3f)", eco, fitted_order, lb_p)
                forecast_vals, conf_int = model.predict(
                    n_periods=FORECAST_STEPS, return_conf_int=True, alpha=0.05
                )

        conf_int = _apply_interval_calibration(model_name_used, np.asarray(forecast_vals, dtype=float), np.asarray(conf_int, dtype=float), interval_calibration)

        # Structural breaks
        break_months = _detect_breaks(y, months)

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
                "forecast_quality": forecast_quality,
                "model_tier_override": model_tier_override,
                "model_name": model_name_used,
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
                "forecast_quality": forecast_quality,
                "model_tier_override": model_tier_override,
                "model_name": model_name_used,
            })

        elapsed = time.perf_counter() - t0
        tier1_times.append(elapsed)
        if elapsed > ECO_TIMING_WARN_S:
            log.warning("%s (Tier 1): took %.1fs, exceeds %.0fs budget", eco, elapsed, ECO_TIMING_WARN_S)

    # ── Tier 2: Model selection from recommendations or Holt-Winters default ──
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

        # Determine which model to use: recommendation or default
        eco_key = str(eco)
        choice = model_choice.get(eco_key, {})
        recommended_model = str(choice.get("model", "holt_winters"))
        model_name_used = recommended_model
        forecast_quality = str(choice.get("confidence", "medium"))

        if recommended_model == "naive":
            # Use naive (last-value) model.
            try:
                forecast_vals, lower_ci, upper_ci = _forecast_naive_model(y, FORECAST_STEPS)
                conf_int = np.column_stack((lower_ci, upper_ci))
                log.info("%s (Tier 2): using naive model from model choice", eco)
            except Exception as exc:
                log.warning("%s (Tier 2): naive model failed (%s), falling back to Holt-Winters", eco, exc)
                model_name_used = "holt_winters"
                hw_forecast, hw_lower, hw_upper = _forecast_holt_winters(y, FORECAST_STEPS)
                forecast_vals = hw_forecast
                conf_int = np.column_stack((hw_lower, hw_upper))
        elif recommended_model == "mean":
            try:
                forecast_vals, lower_ci, upper_ci = _forecast_mean_model(y, FORECAST_STEPS)
                conf_int = np.column_stack((lower_ci, upper_ci))
                log.info("%s (Tier 2): using mean model from model choice", eco)
            except Exception as exc:
                log.warning("%s (Tier 2): mean model failed (%s), falling back to Holt-Winters", eco, exc)
                model_name_used = "holt_winters"
                hw_forecast, hw_lower, hw_upper = _forecast_holt_winters(y, FORECAST_STEPS)
                forecast_vals = hw_forecast
                conf_int = np.column_stack((hw_lower, hw_upper))
        else:
            # Use Holt-Winters (default or if naive failed)
            if model_name_used != "holt_winters":
                model_name_used = "holt_winters"
            hw_forecast, hw_lower, hw_upper = _forecast_holt_winters(y, FORECAST_STEPS)
            forecast_vals = hw_forecast
            conf_int = np.column_stack((hw_lower, hw_upper))

        conf_int = _apply_interval_calibration(model_name_used, np.asarray(forecast_vals, dtype=float), np.asarray(conf_int, dtype=float), interval_calibration)

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
                "forecast_quality": forecast_quality,
                "model_tier_override": "",
                "model_name": model_name_used,
            })

        # Forecast rows
        for fm, fc, lo, hi in zip(future_months, forecast_vals, conf_int[:, 0], conf_int[:, 1]):
            records.append({
                "eco": eco,
                "opening_name": opening_name,
                "month": fm.strftime("%Y-%m"),
                "actual": None,
                "forecast": round(float(fc), 6),
                "lower_ci": round(float(lo), 6),
                "upper_ci": round(float(hi), 6),
                "is_forecast": True,
                "structural_break": False,
                "model_tier": 2,
                "forecast_quality": forecast_quality,
                "model_tier_override": "",
                "model_name": model_name_used,
            })

        elapsed = time.perf_counter() - t0
        tier2_times.append(elapsed)
        if elapsed > ECO_TIMING_WARN_S:
            log.warning("%s (Tier 2): took %.1fs, exceeds %.0fs budget", eco, elapsed, ECO_TIMING_WARN_S)

    # ── Tier 3: descriptive stats ─────────────────────────────────────────────
    log.info("Timeseries: computing descriptive stats for %d Tier-3 ECOs", len(tier3_ecos))
    tier3_df = df[df["eco"].isin(tier3_ecos)]
    tier3_records = []
    for eco, grp in tier3_df.groupby("eco"):
        grp = grp.sort_values("month")
        if len(grp) < 1:
            continue
        tier3_records.append(_run_descriptive_stats(str(eco), grp))

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

    if tier3_records:
        lt_cols = [
            "eco", "opening_name", "eco_group", "model_tier",
            "last_month", "last_win_rate", "mean_win_rate", "std_win_rate",
            "ma3", "trend_direction", "months_available",
        ]
        lt_out = pd.DataFrame(tier3_records, columns=lt_cols)
        lt_out.to_csv(LONG_TAIL_CSV, index=False)
        print(f"Long-tail stats written \u2192 {LONG_TAIL_CSV}  ({len(lt_out)} rows)")

    return out


if __name__ == "__main__":
    run_timeseries()
