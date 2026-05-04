"""Compute and update selection flags in data/openings_catalog.csv.

Reads every data/raw/<ECO>_<YYYY-MM>.json file, aggregates monthly game counts
per ECO, then applies the criteria from config.json:

    is_tracked_core = True   if avg_monthly_games >= min_monthly_games
                              AND months_with_data  >= min_months_data
    is_long_tail    = True   if any raw data exists for the ECO but it does
                              NOT meet is_tracked_core criteria
    model_tier               1 if is_tracked_core, else 3

Rules:
- Idempotent: re-running with the same data produces the same output.
- Existing manual overrides for is_tracked_core=True are preserved when the
  ECO still has data (i.e. we never downgrade an ECO that has data).
- ECOs not found in the raw data keep their current flags unchanged.

Usage:
    python scripts/compute_selection_flags.py [--dry-run]
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
CATALOG_PATH  = ROOT / "data" / "openings_catalog.csv"
RAW_DATA_DIR  = ROOT / "data" / "raw"
CONFIG_PATH   = ROOT / "config.json"


def load_config() -> dict:
    with open(CONFIG_PATH, encoding="utf-8") as f:
        return json.load(f)


def compute_monthly_games() -> dict[str, list[int]]:
    """Return {eco: [game_count_per_month, ...]} from consolidated raw JSON files."""
    eco_months: dict[str, list[int]] = {}

    for fpath in sorted(RAW_DATA_DIR.glob("*.json")):
        try:
            data = json.loads(fpath.read_text(encoding="utf-8"))
        except Exception:
            continue

        if "months" not in data:
            print(f"Warning: {fpath.name} has no 'months' key — skipping (legacy/corrupt)")
            continue

        eco = data.get("eco", fpath.stem)
        for month_data in data["months"].values():
            games = (
                month_data.get("white", 0)
                + month_data.get("draws", 0)
                + month_data.get("black", 0)
            )
            eco_months.setdefault(eco, []).append(games)

    return eco_months


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true",
                        help="Print changes without writing to disk")
    args = parser.parse_args()

    if not CATALOG_PATH.exists():
        print(f"ERROR: {CATALOG_PATH} not found — run build_catalog.py first.")
        return

    config = load_config()
    min_games  = int(config.get("min_monthly_games", 200))
    min_months = int(config.get("min_months_data",   24))

    print(f"Criteria: avg_monthly_games >= {min_games}, months_with_data >= {min_months}")

    eco_months = compute_monthly_games()
    print(f"Found raw data for {len(eco_months)} ECO codes.")

    catalog = pd.read_csv(CATALOG_PATH)
    catalog["eco"] = catalog["eco"].astype(str).str.strip().str.upper()

    changed = 0
    for idx, row in catalog.iterrows():
        eco = str(row["eco"])
        months_data = eco_months.get(eco, [])
        if not months_data:
            continue

        avg_games      = sum(months_data) / len(months_data)
        months_count   = len([g for g in months_data if g > 0])

        new_core = avg_games >= min_games and months_count >= min_months
        new_tail = not new_core  # has data but doesn't meet core criteria
        new_tier = 1 if new_core else 3

        old_core = bool(row.get("is_tracked_core", False))
        old_tail = bool(row.get("is_long_tail",    True))
        old_tier = int(row.get("model_tier",       3))

        if (new_core, new_tail, new_tier) != (old_core, old_tail, old_tier):
            print(
                f"  {eco}: core {old_core}→{new_core}, "
                f"tail {old_tail}→{new_tail}, tier {old_tier}→{new_tier} "
                f"(avg={avg_games:.0f} games/month over {months_count} months)"
            )
            catalog.at[idx, "is_tracked_core"] = new_core
            catalog.at[idx, "is_long_tail"]    = new_tail
            catalog.at[idx, "model_tier"]      = new_tier
            changed += 1

    print(f"\n{changed} entries changed.")

    if changed == 0:
        print("Catalog is already up to date — no writes needed.")
        return

    if args.dry_run:
        print("[dry-run] No changes written.")
        return

    catalog.to_csv(CATALOG_PATH, index=False)
    print(f"Catalog written → {CATALOG_PATH}")


if __name__ == "__main__":
    main()
