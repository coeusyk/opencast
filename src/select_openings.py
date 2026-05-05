"""Compute opening selection flags and model tiers from openings_ts.csv.

Reads data/processed/openings_ts.csv, computes per-ECO statistics, applies
selection rules, and merges results into data/openings_catalog.csv.
"""

import logging
import os

import numpy as np
import pandas as pd

_HERE = os.path.dirname(__file__)
PROCESSED_CSV = os.path.join(_HERE, "..", "data", "processed", "openings_ts.csv")
CATALOG_CSV   = os.path.join(_HERE, "..", "data", "openings_catalog.csv")

MIN_GAMES_CORE     = 1000
MIN_MONTHS_CORE    = 24
MIN_GAMES_LONGTAIL = 100
MIN_GAMES_TIER2    = 500

log = logging.getLogger(__name__)


def _compute_eco_stats(ts: pd.DataFrame) -> pd.DataFrame:
    """Compute per-ECO aggregate statistics from the time series dataframe."""
    rows = []
    for eco, grp in ts.groupby("eco"):
        grp = grp.sort_values("month").reset_index(drop=True)

        avg_monthly_games  = float(grp["total"].mean())
        months_with_data   = int((grp["total"] >= 500).sum())

        # Linear regression slope of white_win_rate over time (index as x)
        y = grp["white_win_rate"].values.astype(float)
        if len(y) >= 2:
            x = np.arange(len(y), dtype=float)
            win_rate_slope = float(np.polyfit(x, np.asarray(y), 1)[0])
        else:
            win_rate_slope = 0.0

        rows.append({
            "eco": eco,
            "avg_monthly_games": avg_monthly_games,
            "months_with_data":  months_with_data,
            "win_rate_slope":    win_rate_slope,
        })
    return pd.DataFrame(rows)


def _apply_selection_rules(stats: pd.DataFrame) -> pd.DataFrame:
    """Apply is_tracked_core, is_long_tail, and model_tier flags to stats."""
    stats = stats.copy()

    stats["is_tracked_core"] = (
        (stats["avg_monthly_games"] >= MIN_GAMES_CORE) &
        (stats["months_with_data"]  >= MIN_MONTHS_CORE)
    )
    stats["is_long_tail"] = (
        (stats["avg_monthly_games"] >= MIN_GAMES_LONGTAIL) &
        (~stats["is_tracked_core"])
    )

    def _tier(row: pd.Series) -> int:
        if row["is_tracked_core"]:
            return 1
        if row["is_long_tail"] and row["avg_monthly_games"] >= MIN_GAMES_TIER2:
            return 2
        if row["is_long_tail"]:
            return 3
        return 3  # everything else gets Tier 3 by default

    stats["model_tier"] = stats.apply(_tier, axis=1)
    return stats


def _compute_data_status(stats_indexed: pd.DataFrame, catalog: pd.DataFrame) -> pd.Series:
    """Return a Series of 'missing' | 'sparse' | 'ok' keyed by ECO code.

    missing — ECO is in the catalog but has no rows in openings_ts.csv
               (i.e. no raw data file was ever ingested).
    sparse  — ECO has some data but fewer than 12 months, which is too thin
               for any meaningful modelling or descriptive stats.
    ok      — ECO has enough data for Tier-1/2/3 processing.
    """
    result = {}
    for eco in catalog["eco"]:
        if eco not in stats_indexed.index:
            result[eco] = "missing"
        elif int(stats_indexed.at[eco, "months_with_data"]) < 12:
            result[eco] = "sparse"
        else:
            result[eco] = "ok"
    return pd.Series(result)


def run_select_openings() -> pd.DataFrame:
    """Compute selection flags and merge into openings_catalog.csv.

    Returns the updated catalog DataFrame.
    """
    ts = pd.read_csv(PROCESSED_CSV)
    log.info("select_openings: loaded %d rows from %s", len(ts), PROCESSED_CSV)

    stats = _compute_eco_stats(ts)
    stats = _apply_selection_rules(stats)

    log.info(
        "select_openings: %d core, %d long-tail, %d other ECOs computed",
        int(stats["is_tracked_core"].sum()),
        int(stats["is_long_tail"].sum()),
        int((~stats["is_tracked_core"] & ~stats["is_long_tail"]).sum()),
    )

    # Load existing catalog
    catalog = pd.read_csv(CATALOG_CSV)

    # For existing catalog rows, update the computed flag columns
    stat_cols = ["is_tracked_core", "is_long_tail", "model_tier"]
    stats_indexed = stats.set_index("eco")

    for col in stat_cols:
        catalog[col] = catalog["eco"].map(
            lambda eco, c=col: stats_indexed.at[eco, c]
            if eco in stats_indexed.index
            else catalog.loc[catalog["eco"] == eco, c].values[0]
        )

    # Compute and store data_status for every catalog ECO
    data_status_series = _compute_data_status(stats_indexed, catalog)
    catalog["data_status"] = catalog["eco"].map(data_status_series).fillna("missing")

    # Append new ECOs found in ts but not yet in catalog
    known_ecos = set(catalog["eco"])
    new_rows = []
    for _, stat_row in stats.iterrows():
        eco = stat_row["eco"]
        if eco in known_ecos:
            continue
        # For newly discovered ECOs we don't have a name or moves — leave blank
        # for a human to fill in; flags are computed from data.
        months = int(stat_row.get("months_with_data", 0))
        new_data_status = "ok" if months >= 12 else ("sparse" if months > 0 else "missing")
        new_rows.append({
            "eco":             eco,
            "name":            "",
            "eco_group":       eco[0],
            "moves":           "",
            "is_tracked_core": bool(stat_row["is_tracked_core"]),
            "is_long_tail":    bool(stat_row["is_long_tail"]),
            "model_tier":      int(stat_row["model_tier"]),
            "data_status":     new_data_status,
        })

    if new_rows:
        log.info("select_openings: appending %d new ECOs to catalog", len(new_rows))
        catalog = pd.concat([catalog, pd.DataFrame(new_rows)], ignore_index=True)

    catalog.to_csv(CATALOG_CSV, index=False)
    log.info("select_openings: catalog updated → %s  (%d rows)", CATALOG_CSV, len(catalog))
    return catalog


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    run_select_openings()
