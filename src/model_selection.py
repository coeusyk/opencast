import json
import logging
import os
from pathlib import Path
from typing import Any

import pandas as pd

_HERE = os.path.dirname(__file__)
CONFIG_JSON = os.path.join(_HERE, "..", "config.json")
CATALOG_CSV = os.path.join(_HERE, "..", "data", "openings_catalog.csv")
EVAL_CSV = os.path.join(_HERE, "..", "data", "output", "model_eval_summary.csv")
MODEL_CHOICE_JSON = os.path.join(_HERE, "..", "data", "output", "model_choice.json")
INTERVAL_CALIBRATION_JSON = os.path.join(_HERE, "..", "data", "output", "interval_calibration.json")
MODEL_SELECTION_CSV = os.path.join(_HERE, "..", "data", "output", "model_selection.csv")

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
log = logging.getLogger(__name__)


def _load_config() -> dict[str, float]:
    with open(CONFIG_JSON) as f:
        cfg = json.load(f)
    return {
        "tier1_mae_threshold": float(cfg.get("tier1_model_mae_threshold_pp", 1.0)),
        "tier2_mae_threshold": float(cfg.get("tier2_model_mae_threshold_pp", 0.5)),
    }


def _mean_mae(eval_df: pd.DataFrame, eco: str, model_name: str) -> float | None:
    rows = eval_df[(eval_df["eco"] == eco) & (eval_df["model_name"] == model_name)]
    if rows.empty:
        return None
    return float(rows["mae_pp"].mean())


def _confidence_label(mae_pp: float | None, coverage_95: float | None) -> str:
    if mae_pp is None or coverage_95 is None:
        return "low"
    if mae_pp <= 0.75 and coverage_95 >= 0.9:
        return "high"
    if mae_pp <= 1.5 and coverage_95 >= 0.8:
        return "medium"
    return "low"


def build_model_choice(eval_csv: Path, catalog_csv: Path, config: dict[str, float]) -> tuple[dict[str, Any], dict[str, Any], pd.DataFrame]:
    if not eval_csv.exists():
        raise FileNotFoundError(f"Evaluation summary not found: {eval_csv}")

    eval_df = pd.read_csv(eval_csv)
    catalog_df = pd.read_csv(catalog_csv)

    records: list[dict[str, Any]] = []
    model_choice: dict[str, Any] = {}

    for catalog_row in catalog_df.itertuples(index=False):
        eco = str(catalog_row.eco)
        tier = int(catalog_row.model_tier)
        if tier not in {1, 2}:
            continue

        eco_eval = eval_df[eval_df["eco"] == eco]
        if eco_eval.empty:
            continue

        naive_mae = _mean_mae(eval_df, eco, "naive")
        mean_mae = _mean_mae(eval_df, eco, "mean")
        arima_mae = _mean_mae(eval_df, eco, "arima")
        hw_mae = _mean_mae(eval_df, eco, "holt_winters")

        if tier == 1:
            if (
                naive_mae is not None
                and arima_mae is not None
                and (naive_mae - arima_mae) >= config["tier1_mae_threshold"]
            ):
                chosen_model = "arima"
                reason = f"ARIMA beats naive by {naive_mae - arima_mae:.2f}pp"
            elif (
                naive_mae is not None
                and hw_mae is not None
                and (naive_mae - hw_mae) >= config["tier2_mae_threshold"]
            ):
                chosen_model = "holt_winters"
                reason = f"ARIMA did not clear threshold; Holt-Winters beats naive by {naive_mae - hw_mae:.2f}pp"
            elif naive_mae is not None:
                chosen_model = "naive"
                reason = "ARIMA/Holt-Winters did not clear thresholds; falling back to naive"
            elif hw_mae is not None:
                chosen_model = "holt_winters"
                reason = "naive unavailable; falling back to Holt-Winters"
            elif arima_mae is not None:
                chosen_model = "arima"
                reason = "naive unavailable; falling back to ARIMA"
            elif mean_mae is not None:
                chosen_model = "mean"
                reason = "naive unavailable; falling back to mean"
            else:
                chosen_model = "naive"
                reason = "tier default fallback"
        else:
            if naive_mae is not None and hw_mae is not None and (naive_mae - hw_mae) >= config["tier2_mae_threshold"]:
                chosen_model = "holt_winters"
                reason = f"Holt-Winters beats naive by {naive_mae - hw_mae:.2f}pp"
            elif mean_mae is not None:
                chosen_model = "mean"
                reason = "Holt-Winters did not clear threshold; falling back to mean"
            else:
                chosen_model = "naive"
                reason = "Holt-Winters did not clear threshold; falling back to naive"

        chosen_rows = eco_eval[eco_eval["model_name"] == chosen_model]
        coverage = float(chosen_rows["coverage_95"].mean()) if not chosen_rows.empty else None
        mae_pp = float(chosen_rows["mae_pp"].mean()) if not chosen_rows.empty else None
        confidence = _confidence_label(mae_pp, coverage)

        model_choice[eco] = {
            "tier": tier,
            "model": chosen_model,
            "confidence": confidence,
            "mae_pp": mae_pp,
            "coverage_95": coverage,
            "reason": reason,
        }
        records.append({
            "eco": eco,
            "model_tier": tier,
            "recommended_model": chosen_model,
            "confidence": confidence,
            "mae_pp": mae_pp,
            "coverage_95": coverage,
            "reason": reason,
        })

    calibration: dict[str, Any] = {}
    grouped = eval_df.groupby(["model_name", "horizon"], as_index=False)["coverage_95"].mean()
    for row in grouped.itertuples(index=False):
        coverage = float(row.coverage_95)
        if coverage <= 0.0:
            scale = 1.0
        else:
            scale = max(0.5, min(2.0, 0.95 / coverage))
        calibration.setdefault(str(row.model_name), {})[str(int(row.horizon))] = round(scale, 4)

    return model_choice, calibration, pd.DataFrame(records)


def main() -> None:
    config = _load_config()
    model_choice, calibration, selection_df = build_model_choice(Path(EVAL_CSV), Path(CATALOG_CSV), config)

    os.makedirs(os.path.dirname(MODEL_CHOICE_JSON), exist_ok=True)
    with open(MODEL_CHOICE_JSON, "w", encoding="utf-8") as f:
        json.dump(model_choice, f, indent=2, sort_keys=True)
    with open(INTERVAL_CALIBRATION_JSON, "w", encoding="utf-8") as f:
        json.dump(calibration, f, indent=2, sort_keys=True)
    selection_df.to_csv(MODEL_SELECTION_CSV, index=False)

    log.info("Model choice written -> %s (%d ECOs)", MODEL_CHOICE_JSON, len(model_choice))
    log.info("Interval calibration written -> %s", INTERVAL_CALIBRATION_JSON)
    log.info("Model selection audit written -> %s", MODEL_SELECTION_CSV)


if __name__ == "__main__":
    main()
