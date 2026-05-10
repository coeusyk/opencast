import json
import os

import pandas as pd

_SRC_ROOT = os.path.dirname(os.path.dirname(__file__))
_REPO_ROOT = os.path.dirname(_SRC_ROOT)
FORECASTS_CSV = os.path.join(_REPO_ROOT, "data", "output", "forecasts.csv")
ENGINE_CSV = os.path.join(_REPO_ROOT, "data", "output", "engine_delta.csv")
CATALOG_CSV = os.path.join(_REPO_ROOT, "data", "openings_catalog.csv")
FINDINGS_JSON = os.path.join(_REPO_ROOT, "findings", "findings.json")
NARRATIVES_JSON = os.path.join(_REPO_ROOT, "findings", "narratives.json")
LONG_TAIL_CSV = os.path.join(_REPO_ROOT, "data", "output", "long_tail_stats.csv")
MOVE_STATS_CSV = os.path.join(_REPO_ROOT, "data", "output", "move_stats.csv")
OPENING_LINES_JSON = os.path.join(_REPO_ROOT, "data", "opening_lines.json")
ICON_SOURCE_PNG = os.path.join(_REPO_ROOT, "opencast_icon.png")
CONFIG_JSON = os.path.join(_REPO_ROOT, "config.json")
OUTPUT_DIR = os.path.join(_REPO_ROOT, "data", "output", "dashboard")
ASSETS_DIR = os.path.join(OUTPUT_DIR, "assets")

FORECAST_COLUMNS = [
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


def _safe_read_forecasts() -> pd.DataFrame:
    try:
        df = pd.read_csv(FORECASTS_CSV)
    except Exception:
        return pd.DataFrame(columns=FORECAST_COLUMNS)

    for col in FORECAST_COLUMNS:
        if col not in df.columns:
            df[col] = None
    return df


def _load_findings_json() -> dict | None:
    try:
        with open(FINDINGS_JSON, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _load_narratives_json() -> dict:
    try:
        with open(NARRATIVES_JSON, encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict) or "per_opening" not in data:
            return {"per_opening": {}}
        return data
    except Exception:
        return {"per_opening": {}}


def _load_runtime_config() -> dict:
    try:
        with open(CONFIG_JSON, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _top_lines_for_opening(move_stats_df: pd.DataFrame | None, eco: str, limit: int = 3) -> list[dict]:
    if move_stats_df is None or move_stats_df.empty or "eco" not in move_stats_df.columns:
        return []

    sub = move_stats_df[move_stats_df["eco"].astype(str) == str(eco)].copy()
    if sub.empty or "month" not in sub.columns:
        return []

    latest_month = str(sub["month"].astype(str).max())
    latest = sub[sub["month"].astype(str) == latest_month].copy()
    if latest.empty:
        return []

    for col in ("games", "white_win_rate", "share_of_games", "delta_share_12m", "delta_wr_12m"):
        if col not in latest.columns:
            latest[col] = None

    latest["games"] = pd.to_numeric(latest["games"], errors="coerce").fillna(0)
    latest["white_win_rate"] = pd.to_numeric(latest["white_win_rate"], errors="coerce")
    latest["share_of_games"] = pd.to_numeric(latest["share_of_games"], errors="coerce").fillna(0.0)
    latest["delta_share_12m"] = pd.to_numeric(latest["delta_share_12m"], errors="coerce")
    latest["delta_wr_12m"] = pd.to_numeric(latest["delta_wr_12m"], errors="coerce")

    cfg = _load_runtime_config()
    min_games = int(cfg.get("move_line_min_games", 5))
    min_share = float(cfg.get("move_line_min_share", 0.005))

    latest = latest[(latest["games"] >= min_games) & (latest["share_of_games"] >= min_share)].copy()
    if latest.empty:
        return []

    latest["trend_score"] = (
        latest["share_of_games"] * 0.65
        + latest["delta_share_12m"].abs().fillna(0.0) * 8.0
        + latest["delta_wr_12m"].abs().fillna(0.0) * 20.0
    )

    top = latest.sort_values(["trend_score", "games"], ascending=[False, False]).head(limit)

    rows: list[dict] = []
    for _, r in top.iterrows():
        rows.append(
            {
                "month": latest_month,
                "uci": str(r.get("uci", "")),
                "san": str(r.get("san", "")),
                "games": int(r.get("games", 0)) if pd.notna(r.get("games")) else 0,
                "white_win_rate": float(r["white_win_rate"]) if pd.notna(r.get("white_win_rate")) else None,
                "share_of_games": float(r.get("share_of_games", 0.0)),
                "delta_share_12m": float(r["delta_share_12m"]) if pd.notna(r.get("delta_share_12m")) else None,
                "delta_wr_12m": float(r["delta_wr_12m"]) if pd.notna(r.get("delta_wr_12m")) else None,
            }
        )

    return rows


def _serialize_openings_data(
    forecasts: pd.DataFrame,
    engine_df: pd.DataFrame,
    catalog: pd.DataFrame,
    findings_json: dict | None,
    narratives: dict | None = None,
    long_tail_df: pd.DataFrame | None = None,
    move_stats_df: pd.DataFrame | None = None,
    trend_signals: dict | None = None,
) -> dict[str, dict]:
    fallback_narrative = "No analysis available yet."
    if narratives and "per_opening" in narratives:
        per_opening = narratives["per_opening"]
    elif findings_json:
        per_opening = findings_json.get("per_opening", {})
    else:
        per_opening = {}

    ecos = catalog["eco"].astype(str).tolist() if (not catalog.empty and "eco" in catalog.columns) else []
    if not ecos and not forecasts.empty and "eco" in forecasts.columns:
        ecos = sorted(forecasts["eco"].dropna().astype(str).unique().tolist())

    serialized: dict[str, dict] = {}

    for eco in ecos:
        fc_eco = forecasts[forecasts["eco"] == eco].copy()
        if not fc_eco.empty:
            fc_eco = fc_eco.sort_values("month")

        cat_row = catalog[catalog["eco"] == eco] if not catalog.empty else pd.DataFrame()
        name = (
            str(cat_row["name"].iloc[0])
            if (not cat_row.empty and "name" in cat_row.columns)
            else (str(fc_eco["opening_name"].iloc[0]) if not fc_eco.empty else eco)
        )

        model_tier = None
        if not cat_row.empty and "model_tier" in cat_row.columns:
            try:
                model_tier = int(cat_row["model_tier"].iloc[0])
            except Exception:
                model_tier = None

        actuals_rows = fc_eco[fc_eco["is_forecast"] == False] if not fc_eco.empty else pd.DataFrame()
        forecast_rows = fc_eco[fc_eco["is_forecast"] == True] if not fc_eco.empty else pd.DataFrame()

        actuals = []
        for _, row in actuals_rows.iterrows():
            if pd.notna(row.get("actual")):
                actuals.append({"month": str(row["month"]), "win_rate": float(row["actual"])})

        forecast = []
        for _, row in forecast_rows.iterrows():
            forecast.append(
                {
                    "month": str(row["month"]),
                    "value": float(row["forecast"]) if pd.notna(row.get("forecast")) else None,
                    "lower": float(row["lower_ci"]) if pd.notna(row.get("lower_ci")) else None,
                    "upper": float(row["upper_ci"]) if pd.notna(row.get("upper_ci")) else None,
                }
            )

        forecast_quality = None
        model_name = None
        if not forecast_rows.empty and "forecast_quality" in forecast_rows.columns:
            qual = forecast_rows["forecast_quality"].dropna().astype(str)
            if not qual.empty:
                forecast_quality = str(qual.iloc[0]).lower()
        if not forecast_rows.empty and "model_name" in forecast_rows.columns:
            names = forecast_rows["model_name"].dropna().astype(str)
            if not names.empty:
                model_name = str(names.iloc[0])

        structural_breaks = []
        if not fc_eco.empty and "structural_break" in fc_eco.columns:
            structural_breaks = sorted(
                fc_eco[fc_eco["structural_break"] == True]["month"].astype(str).dropna().unique().tolist()
            )

        ed_row = engine_df[engine_df["eco"] == eco] if not engine_df.empty else pd.DataFrame()
        if ed_row.empty:
            engine_cp = None
            p_engine = None
            human_win_rate = None
            delta = None
            interpretation = None
        else:
            engine_cp = int(ed_row["engine_cp"].iloc[0]) if pd.notna(ed_row["engine_cp"].iloc[0]) else None
            p_engine = float(ed_row["p_engine"].iloc[0]) if pd.notna(ed_row["p_engine"].iloc[0]) else None
            human_win_rate = (
                float(ed_row["human_win_rate_2000"].iloc[0])
                if pd.notna(ed_row["human_win_rate_2000"].iloc[0])
                else None
            )
            delta = float(ed_row["delta"].iloc[0]) if pd.notna(ed_row["delta"].iloc[0]) else None
            interpretation = str(ed_row["interpretation"].iloc[0]) if pd.notna(ed_row["interpretation"].iloc[0]) else None

        narrative = per_opening.get(eco, fallback_narrative)

        lt_stats: dict = {}
        if model_tier == 3 and long_tail_df is not None and not long_tail_df.empty:
            lt_row = long_tail_df[long_tail_df["eco"] == eco]
            if not lt_row.empty:
                r = lt_row.iloc[0]
                lt_stats = {
                    "last_month": str(r.get("last_month", "")),
                    "last_win_rate": float(r["last_win_rate"]) if pd.notna(r.get("last_win_rate")) else None,
                    "mean_win_rate": float(r["mean_win_rate"]) if pd.notna(r.get("mean_win_rate")) else None,
                    "std_win_rate": float(r["std_win_rate"]) if pd.notna(r.get("std_win_rate")) else None,
                    "ma3": float(r["ma3"]) if pd.notna(r.get("ma3")) else None,
                    "trend_direction": str(r.get("trend_direction", "flat")),
                    "months_available": int(r["months_available"]) if pd.notna(r.get("months_available")) else None,
                }

        data_status = "ok"
        if not cat_row.empty and "data_status" in cat_row.columns:
            data_status = str(cat_row["data_status"].iloc[0])

        sig = (trend_signals or {}).get(eco)
        lines_driving_trend = _top_lines_for_opening(move_stats_df, eco)
        if model_tier == 3:
            forecast_quality = None
            model_name = None
        serialized[eco] = {
            "name": name,
            "eco_group": eco[0] if eco else None,
            "model_tier": model_tier,
            "data_status": data_status,
            "actuals": actuals,
            "forecast": forecast,
            "structural_breaks": structural_breaks,
            "engine_cp": engine_cp,
            "p_engine": p_engine,
            "human_win_rate": human_win_rate,
            "delta": delta,
            "interpretation": interpretation,
            "narrative": str(narrative) if narrative is not None else fallback_narrative,
            "trend_direction": sig.direction if sig else "stable",
            "trend_slope_per_month": sig.slope_per_month if sig else 0.0,
            "trend_r_squared": sig.r_squared if sig else 0.0,
            "trend_confidence": sig.confidence if sig else "low",
            "trend_streak_months": sig.sustained_months if sig else 0,
            "forecast_quality": forecast_quality,
            "model_name": model_name,
            "lines_driving_trend": lines_driving_trend,
            **lt_stats,
        }

    return serialized