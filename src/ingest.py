import json
import os
from pathlib import Path

import numpy as np
import pandas as pd

_HERE = os.path.dirname(__file__)
RAW_DIR = os.path.join(_HERE, "..", "data", "raw")
PROCESSED_DIR = os.path.join(_HERE, "..", "data", "processed")
OPENINGS_JSON = os.path.join(_HERE, "..", "openings.json")
CATALOG_CSV   = os.path.join(_HERE, "..", "data", "openings_catalog.csv")
OUTPUT_CSV    = os.path.join(PROCESSED_DIR, "openings_ts.csv")
LONG_TAIL_CSV = os.path.join(_HERE, "..", "data", "output", "long_tail_stats.csv")

RATING_BRACKET = 2000
LOW_CONFIDENCE_THRESHOLD = 2000


def _load_min_games() -> int:
    config_path = os.path.join(_HERE, "..", "config.json")
    with open(config_path, encoding="utf-8") as f:
        return int(json.load(f).get("min_monthly_games", 500))


def _load_name_map() -> dict:
    with open(OPENINGS_JSON) as f:
        openings = json.load(f)
    return {o["eco"]: o["name"] for o in openings}


def _compute_long_tail_stats(df: pd.DataFrame) -> pd.DataFrame:
    """Compute descriptive stats for long-tail openings from catalog."""
    if not os.path.exists(CATALOG_CSV):
        return pd.DataFrame(columns=["eco", "name", "last_year_win_rate",
                                     "total_games_last_year", "trend_direction"])

    catalog = pd.read_csv(CATALOG_CSV)
    long_tail_ecos = set(
        catalog.loc[catalog["is_long_tail"] == True, "eco"]
    )

    if not long_tail_ecos:
        return pd.DataFrame(columns=["eco", "name", "last_year_win_rate",
                                     "total_games_last_year", "trend_direction"])

    name_map = catalog.set_index("eco")["name"].to_dict()

    rows = []
    for eco in long_tail_ecos:
        grp = df[df["eco"] == eco].sort_values("month")
        if grp.empty:
            continue

        last12 = grp.tail(12)
        last_year_win_rate    = float(last12["white_win_rate"].mean())
        total_games_last_year = int(last12["total"].sum())

        # Slope for trend direction
        y = last12["white_win_rate"].values.astype(float)
        if len(y) >= 2:
            x = np.arange(len(y), dtype=float)
            slope = float(np.polyfit(x, y, 1)[0])
        else:
            slope = 0.0

        if slope > 0.001:
            trend_direction = "rising"
        elif slope < -0.001:
            trend_direction = "falling"
        else:
            trend_direction = "stable"

        rows.append({
            "eco":                  eco,
            "name":                 name_map.get(eco, eco),
            "last_year_win_rate":   round(last_year_win_rate, 6),
            "total_games_last_year": total_games_last_year,
            "trend_direction":      trend_direction,
        })

    return pd.DataFrame(rows)


def ingest() -> pd.DataFrame:
    name_map = _load_name_map()
    min_games = _load_min_games()
    os.makedirs(PROCESSED_DIR, exist_ok=True)

    rows = []
    for fpath in sorted(Path(RAW_DIR).glob("*.json")):
        try:
            with open(fpath, encoding="utf-8") as f:
                file_data = json.load(f)
        except Exception:
            continue

        if "months" not in file_data:
            continue

        eco = file_data.get("eco", fpath.stem)

        for month, data in sorted(file_data["months"].items()):
            white = data.get("white", 0)
            draws = data.get("draws", 0)
            black = data.get("black", 0)
            total = white + draws + black

            if total < min_games:
                continue

            rows.append({
                "month": month,
                "eco": eco,
                "opening_name": name_map.get(eco, eco),
                "rating_bracket": RATING_BRACKET,
                "white": white,
                "draws": draws,
                "black": black,
                "total": total,
                "white_win_rate": white / total,
                "low_confidence": total < LOW_CONFIDENCE_THRESHOLD,
            })

    df = pd.DataFrame(rows)
    df.to_csv(OUTPUT_CSV, index=False)
    print(f"Ingested {len(df)} rows \u2192 {OUTPUT_CSV}")

    # Write long-tail stats
    os.makedirs(os.path.dirname(LONG_TAIL_CSV), exist_ok=True)
    long_tail_df = _compute_long_tail_stats(df)
    long_tail_df.to_csv(LONG_TAIL_CSV, index=False)
    print(f"Long-tail stats written \u2192 {LONG_TAIL_CSV}  ({len(long_tail_df)} rows)")

    return df


if __name__ == "__main__":
    ingest()
