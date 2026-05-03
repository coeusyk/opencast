"""Build or update data/openings_catalog.csv from an ECO reference source.

Usage:
    python scripts/build_catalog.py [--eco-csv PATH]

Without --eco-csv, runs in read-only mode and prints the current catalog stats.
With --eco-csv, merges the CSV (columns: eco, name, eco_group, moves) into the
catalog, adding any missing entries with default flags:
    is_tracked_core = False
    is_long_tail    = True
    model_tier      = 3

Existing rows are preserved; flags are never downgraded by this script
(use compute_selection_flags.py to update based on data).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
CATALOG_PATH = ROOT / "data" / "openings_catalog.csv"

REQUIRED_COLS = ["eco", "name", "eco_group", "moves",
                 "is_tracked_core", "is_long_tail", "model_tier"]

DEFAULTS = {
    "is_tracked_core": False,
    "is_long_tail": True,
    "model_tier": 3,
}


def load_catalog() -> pd.DataFrame:
    if CATALOG_PATH.exists():
        df = pd.read_csv(CATALOG_PATH)
        for col in REQUIRED_COLS:
            if col not in df.columns:
                df[col] = DEFAULTS.get(col, None)
        return df[REQUIRED_COLS]
    return pd.DataFrame(columns=REQUIRED_COLS)


def merge_eco_reference(catalog: pd.DataFrame, eco_csv: Path) -> pd.DataFrame:
    ref = pd.read_csv(eco_csv)
    missing_ref_cols = {"eco", "name"} - set(ref.columns)
    if missing_ref_cols:
        print(f"ERROR: eco-csv is missing columns: {missing_ref_cols}", file=sys.stderr)
        sys.exit(1)

    ref["eco"] = ref["eco"].astype(str).str.strip().str.upper()
    catalog["eco"] = catalog["eco"].astype(str).str.strip().str.upper()

    existing_ecos = set(catalog["eco"])
    new_rows = []
    for _, row in ref.iterrows():
        eco = str(row["eco"])
        if eco in existing_ecos:
            continue
        new_rows.append({
            "eco": eco,
            "name": str(row.get("name", eco)),
            "eco_group": str(row.get("eco_group", eco[0] if eco else "")),
            "moves": str(row.get("moves", "")),
            "is_tracked_core": DEFAULTS["is_tracked_core"],
            "is_long_tail": DEFAULTS["is_long_tail"],
            "model_tier": DEFAULTS["model_tier"],
        })

    if new_rows:
        new_df = pd.DataFrame(new_rows, columns=REQUIRED_COLS)
        catalog = pd.concat([catalog, new_df], ignore_index=True)
        print(f"Added {len(new_rows)} new ECO entries.")
    else:
        print("No new ECO entries to add — catalog is already up to date.")

    return catalog.sort_values("eco").reset_index(drop=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--eco-csv", type=Path, default=None,
                        help="CSV with columns: eco, name[, eco_group, moves]")
    args = parser.parse_args()

    catalog = load_catalog()

    if args.eco_csv:
        catalog = merge_eco_reference(catalog, args.eco_csv)
        CATALOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        catalog.to_csv(CATALOG_PATH, index=False)
        print(f"Catalog written → {CATALOG_PATH}  ({len(catalog)} entries)")
    else:
        print(f"Catalog at: {CATALOG_PATH}")
        print(f"  Total entries  : {len(catalog)}")
        print(f"  is_tracked_core: {catalog['is_tracked_core'].sum() if not catalog.empty else 0}")
        print(f"  is_long_tail   : {catalog['is_long_tail'].sum() if not catalog.empty else 0}")
        tiers = catalog["model_tier"].value_counts().sort_index() if not catalog.empty else {}
        for tier, count in (tiers.items() if hasattr(tiers, 'items') else []):
            print(f"  Tier {tier}         : {count}")


if __name__ == "__main__":
    main()
