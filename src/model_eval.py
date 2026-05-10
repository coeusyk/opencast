"""
Track 1: Offline rolling-origin model evaluation.

This module compares forecasting models (naive, mean, ARIMA, Holt-Winters)
across Tier 1 and 2 openings using rolling-origin backtests. It is NOT
invoked from main.py by default; instead, run via:
  - `python -m src.model_eval`
  - Or via separate eval.yml GitHub Actions workflow

Output: data/output/model_eval_summary.csv
  Columns: eco, model_name, horizon, mae_pp, rmse_pp, coverage_95, n_samples
"""

import json
import logging
import os
from pathlib import Path
from typing import Sequence

import numpy as np
import pandas as pd
from statsmodels.tsa.holtwinters import ExponentialSmoothing

import pmdarima as pm
import warnings

warnings.filterwarnings("ignore")

_HERE = os.path.dirname(__file__)
PROCESSED_CSV = os.path.join(_HERE, "..", "data", "processed", "openings_ts.csv")
CATALOG_CSV = os.path.join(_HERE, "..", "data", "openings_catalog.csv")
CONFIG_JSON = os.path.join(_HERE, "..", "config.json")
OUTPUT_CSV = os.path.join(_HERE, "..", "data", "output", "model_eval_summary.csv")

REQUIRED_TS_COLUMNS = {"eco", "month", "white_win_rate", "total"}
REQUIRED_CATALOG_COLUMNS = {"eco", "model_tier"}

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
log = logging.getLogger(__name__)


def _load_config() -> dict:
    """Load evaluation configuration from config.json."""
    with open(CONFIG_JSON) as f:
        cfg = json.load(f)
    return {
        "min_history": cfg.get("eval_min_history_months", 30),
        "start_offset": cfg.get("eval_start_offset_months", 24),
        "horizons": cfg.get("eval_horizons", [1, 2, 3]),
    }


def _forecast_naive(y: np.ndarray, steps: int) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Naive forecast: repeat last value with symmetric bounds."""
    forecast = np.full(steps, y[-1], dtype=float)
    residual_std = float(np.std(y, ddof=1)) if len(y) > 1 else 0.0
    half_ci = 1.96 * residual_std
    return forecast, forecast - half_ci, forecast + half_ci


def _forecast_mean(y: np.ndarray, steps: int) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Mean forecast: use mean of the trailing 12 months when available."""
    baseline = y[-12:] if len(y) >= 12 else y
    mean_value = float(np.mean(baseline))
    forecast = np.full(steps, mean_value, dtype=float)
    residuals = baseline - mean_value
    residual_std = float(np.std(residuals, ddof=1)) if len(residuals) > 1 else 0.0
    half_ci = 1.96 * residual_std
    return forecast, forecast - half_ci, forecast + half_ci


def _forecast_arima(y: np.ndarray, steps: int) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """ARIMA forecast via pmdarima auto_arima."""
    try:
        model = pm.auto_arima(
            y,
            d=None,
            start_p=0, max_p=3,
            start_q=0, max_q=3,
            information_criterion="aic",
            stepwise=True,
            suppress_warnings=True,
            error_action="ignore",
        )
        forecast, conf_int = model.predict(n_periods=steps, return_conf_int=True, alpha=0.05)
        forecast = np.asarray(forecast, dtype=float)
        conf_int = np.asarray(conf_int, dtype=float)
        return forecast, conf_int[:, 0], conf_int[:, 1]
    except Exception as exc:
        log.debug("ARIMA fit failed: %s, falling back to mean", exc)
        return _forecast_mean(y, steps)


def _forecast_holt_winters(y: np.ndarray, steps: int) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Holt-Winters (additive trend, no seasonality)."""
    try:
        hw_fit = ExponentialSmoothing(y, trend="add", seasonal=None).fit()
        forecast = np.asarray(hw_fit.forecast(steps), dtype=float)
        resid = np.asarray(hw_fit.resid, dtype=float)
        residual_std = float(np.std(resid, ddof=1)) if len(resid) > 1 else 0.0
        half_ci = 1.96 * residual_std
        return forecast, forecast - half_ci, forecast + half_ci
    except Exception as exc:
        log.debug("Holt-Winters fit failed: %s, falling back to mean", exc)
        return _forecast_mean(y, steps)


def _iter_candidate_models(tier: int, models: Sequence[str] | None) -> list[str]:
    """Restrict candidate models by tier to keep evaluation within CI budget."""
    default_models = ["naive", "mean", "arima", "holt_winters"]
    if models is None:
        return default_models
    allowed = set(default_models)
    return [model_name for model_name in models if model_name in allowed]


def run_model_eval(
    ts_csv: Path,
    catalog_csv: Path,
    output_csv: Path,
    models: Sequence[str] | None = None,
    min_history_months: int = 30,
    start_offset_months: int = 24,
) -> None:
    """
    Execute rolling-origin backtests across Tier 1/2 openings.

    For each opening, train on windows [0:24], [0:25], ..., [0:T-3],
    forecast h steps ahead, and compute metrics.

    Writes summary CSV with columns: eco, model_name, horizon, mae_pp, rmse_pp, coverage_95, n_samples
    """
    df = pd.read_csv(ts_csv)
    catalog = pd.read_csv(catalog_csv)

    missing_ts = REQUIRED_TS_COLUMNS - set(df.columns)
    if missing_ts:
        raise ValueError(f"openings_ts.csv missing required columns: {sorted(missing_ts)}")
    missing_catalog = REQUIRED_CATALOG_COLUMNS - set(catalog.columns)
    if missing_catalog:
        raise ValueError(f"openings_catalog.csv missing required columns: {sorted(missing_catalog)}")

    eval_catalog = catalog[catalog["model_tier"].isin([1, 2])].copy()

    df["month"] = pd.to_datetime(df["month"])
    horizons = tuple(sorted({1, 2, 3}))
    max_horizon = max(horizons)

    results = []

    for row in eval_catalog.itertuples(index=False):
        eco = str(row.eco)
        tier = int(row.model_tier)
        candidate_models = _iter_candidate_models(tier, models)
        eco_df = df[df["eco"] == eco].sort_values("month").reset_index(drop=True)
        n_total = len(eco_df)

        if n_total < min_history_months:
            log.info("%s: only %d points (< %d), skipping", eco, n_total, min_history_months)
            continue

        y = np.asarray(eco_df["white_win_rate"].values, dtype=float)

        for train_end in range(start_offset_months, n_total - max_horizon):
            train_y = y[:train_end]
            actuals = {horizon: float(y[train_end + horizon]) for horizon in horizons}

            for model_name in candidate_models:
                try:
                    if model_name == "naive":
                        forecasts, lower, upper = _forecast_naive(train_y, max_horizon)
                    elif model_name == "mean":
                        forecasts, lower, upper = _forecast_mean(train_y, max_horizon)
                    elif model_name == "arima":
                        forecasts, lower, upper = _forecast_arima(train_y, max_horizon)
                    else:
                        forecasts, lower, upper = _forecast_holt_winters(train_y, max_horizon)
                except Exception as exc:
                    log.debug("%s model=%s: fit failed (%s)", eco, model_name, exc)
                    continue

                for horizon in horizons:
                    index = horizon - 1
                    prediction = float(forecasts[index])
                    actual_value = actuals[horizon]
                    results.append({
                        "eco": eco,
                        "model_name": model_name,
                        "horizon": horizon,
                        "ae": abs(prediction - actual_value),
                        "se": (prediction - actual_value) ** 2,
                        "covered": float(lower[index] <= actual_value <= upper[index]),
                    })

    # Aggregate metrics per (eco, model_name, horizon)
    if not results:
        log.warning("No evaluation results collected")
        return

    results_df = pd.DataFrame(results)
    summary = results_df.groupby(["eco", "model_name", "horizon"]).agg({
        "ae": "mean",
        "se": "mean",
        "covered": "mean",
    }).reset_index()

    summary["mae_pp"] = summary["ae"] * 100  # Convert to percentage points
    summary["rmse_pp"] = np.sqrt(summary["se"]) * 100
    summary["coverage_95"] = summary["covered"]
    summary["n_samples"] = results_df.groupby(["eco", "model_name", "horizon"]).size().values

    summary = summary[["eco", "model_name", "horizon", "mae_pp", "rmse_pp", "coverage_95", "n_samples"]]
    summary = summary.sort_values(["eco", "model_name", "horizon"])

    os.makedirs(os.path.dirname(output_csv), exist_ok=True)
    summary.to_csv(output_csv, index=False)
    log.info("Model evaluation summary written → %s (%d rows)", output_csv, len(summary))


def main() -> None:
    """CLI entry point for offline model evaluation."""
    config = _load_config()
    log.info(
        "Model evaluation: min_history=%d, start_offset=%d, horizons=%s",
        config["min_history"],
        config["start_offset"],
        [1, 2, 3],
    )
    run_model_eval(
        Path(PROCESSED_CSV),
        Path(CATALOG_CSV),
        Path(OUTPUT_CSV),
        min_history_months=config["min_history"],
        start_offset_months=config["start_offset"],
    )


if __name__ == "__main__":
    main()
