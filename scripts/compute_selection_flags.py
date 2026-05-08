"""Compute and update selection flags using coverage-ratio criteria.

Reads consolidated data/raw/<ECO>.json files and computes per-ECO metrics.
Tier assignment is controlled entirely by config.json thresholds:

    Tier 1 (tracked core):
        total_months >= min_months_data
        and coverage_ratio >= min_coverage_ratio

    Tier 2 (descriptive only):
        total_months >= min_months_data
        and coverage_ratio >= min_coverage_ratio_tier2

    Tier 3 (long tail):
        otherwise

Where coverage_ratio = months_above_threshold / total_months, and a month is
"above threshold" when games in that month >= min_monthly_games.

Usage:
    python scripts/compute_selection_flags.py [--dry-run] [--prune-noncore] [--prune-below-threshold-months]
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
FLAGS_PATH    = ROOT / "data" / "selection_flags.csv"


def load_config() -> dict:
    with open(CONFIG_PATH, encoding="utf-8") as f:
        return json.load(f)


def compute_monthly_games() -> dict[str, dict[str, int]]:
    """Return {eco: {month: game_count}} from consolidated raw JSON files."""
    eco_months: dict[str, dict[str, int]] = {}

    for fpath in sorted(RAW_DATA_DIR.glob("*.json")):
        try:
            data = json.loads(fpath.read_text(encoding="utf-8"))
        except Exception:
            continue

        if "months" not in data:
            print(f"Warning: {fpath.name} has no 'months' key — skipping (legacy/corrupt)")
            continue

        eco = data.get("eco", fpath.stem)
        for month, month_data in data["months"].items():
            games = (
                month_data.get("white", 0)
                + month_data.get("draws", 0)
                + month_data.get("black", 0)
            )
            eco_months.setdefault(eco, {})[month] = games

    return eco_months


def prune_below_threshold_months(min_games: int, dry_run: bool) -> tuple[int, int]:
    """Remove months with total games < min_games from consolidated raw files.

    Returns (months_removed, files_removed).
    """
    months_removed = 0
    files_removed = 0

    for fpath in sorted(RAW_DATA_DIR.glob("*.json")):
        try:
            data = json.loads(fpath.read_text(encoding="utf-8"))
        except Exception:
            continue

        months = data.get("months")
        if not isinstance(months, dict):
            continue

        keep_months: dict[str, dict] = {}
        removed_here = 0
        for month, month_data in months.items():
            total = (
                month_data.get("white", 0)
                + month_data.get("draws", 0)
                + month_data.get("black", 0)
            )
            if total >= min_games:
                keep_months[month] = month_data
            else:
                removed_here += 1

        if removed_here == 0:
            continue

        months_removed += removed_here
        if keep_months:
            data["months"] = keep_months
            if dry_run:
                print(f"  [dry-run] would prune {removed_here} month(s) in {fpath.name}")
            else:
                fpath.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
                print(f"  pruned {removed_here} month(s) in {fpath.name}")
        else:
            files_removed += 1
            if dry_run:
                print(f"  [dry-run] would remove {fpath.name} (no qualifying months remain)")
            else:
                fpath.unlink()
                print(f"  removed {fpath.name} (no qualifying months remain)")

    return months_removed, files_removed


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true",
                        help="Print changes without writing to disk")
    parser.add_argument(
        "--prune-noncore",
        action="store_true",
        help="Delete data/raw/<ECO>.json files for ECOs that are not Tier 1",
    )
    parser.add_argument(
        "--prune-below-threshold-months",
        action="store_true",
        help="Delete per-ECO months where monthly total is below min_monthly_games",
    )
    args = parser.parse_args()

    if not CATALOG_PATH.exists():
        print(f"ERROR: {CATALOG_PATH} not found — run build_catalog.py first.")
        return

    config = load_config()
    min_games = int(config.get("min_monthly_games", 400))
    min_months = int(config.get("min_months_data", 24))
    min_coverage_ratio = float(config.get("min_coverage_ratio", 0.75))
    min_coverage_ratio_tier2 = float(config.get("min_coverage_ratio_tier2", 0.4))

    print(
        "Criteria: "
        f"min_monthly_games={min_games}, "
        f"min_months_data={min_months}, "
        f"min_coverage_ratio={min_coverage_ratio:.2f}, "
        f"min_coverage_ratio_tier2={min_coverage_ratio_tier2:.2f}"
    )

    if args.prune_below_threshold_months:
        print("Pruning below-threshold months before tier computation:")
        months_removed, files_removed = prune_below_threshold_months(
            min_games=min_games,
            dry_run=args.dry_run,
        )
        mode = "[dry-run] " if args.dry_run else ""
        print(f"  {mode}months removed: {months_removed}")
        print(f"  {mode}files removed: {files_removed}")

    eco_months = compute_monthly_games()
    print(f"Found raw data for {len(eco_months)} ECO codes.")

    catalog = pd.read_csv(CATALOG_PATH)
    catalog["eco"] = catalog["eco"].astype(str).str.strip().str.upper()

    changed = 0
    flags_rows: list[dict] = []
    dropped_from_old_tier1: list[str] = []

    tier1_count = 0
    tier2_count = 0
    tier3_count = 0

    for idx, row in catalog.iterrows():
        eco = str(row["eco"])
        monthly_games = eco_months.get(eco, {})
        if not monthly_games:
            continue

        total_months = len(monthly_games)
        months_above = sum(1 for v in monthly_games.values() if v >= min_games)
        coverage_ratio = months_above / total_months if total_months > 0 else 0.0
        avg_games = sum(monthly_games.values()) / total_months if total_months > 0 else 0.0

        new_core = total_months >= min_months and coverage_ratio >= min_coverage_ratio
        if new_core:
            new_tier = 1
        elif total_months >= min_months and coverage_ratio >= min_coverage_ratio_tier2:
            new_tier = 2
        else:
            new_tier = 3

        new_tail = not new_core

        if new_tier == 1:
            tier1_count += 1
        elif new_tier == 2:
            tier2_count += 1
        else:
            tier3_count += 1

        old_style_tier1 = total_months >= min_months and avg_games >= min_games
        if old_style_tier1 and not new_core:
            dropped_from_old_tier1.append(eco)

        flags_rows.append(
            {
                "eco": eco,
                "tier": new_tier,
                "total_months": total_months,
                "months_above_threshold": months_above,
                "coverage_ratio": round(coverage_ratio, 6),
                "avg_monthly_games": round(avg_games, 2),
                "is_tracked_core": bool(new_core),
            }
        )

        old_core = bool(row.get("is_tracked_core", False))
        old_tail = bool(row.get("is_long_tail",    True))
        old_tier = int(row.get("model_tier",       3))

        if (new_core, new_tail, new_tier) != (old_core, old_tail, old_tier):
            print(
                f"  {eco}: core {old_core}→{new_core}, "
                f"tail {old_tail}→{new_tail}, tier {old_tier}→{new_tier} "
                f"(coverage={coverage_ratio:.2f}, avg={avg_games:.0f}, months={total_months})"
            )
            catalog.at[idx, "is_tracked_core"] = new_core
            catalog.at[idx, "is_long_tail"]    = new_tail
            catalog.at[idx, "model_tier"]      = new_tier
            changed += 1

    flags_df = pd.DataFrame(
        flags_rows,
        columns=[
            "eco",
            "tier",
            "total_months",
            "months_above_threshold",
            "coverage_ratio",
            "avg_monthly_games",
            "is_tracked_core",
        ],
    ).sort_values("eco")

    noncore_ecos = set(flags_df.loc[flags_df["is_tracked_core"] != True, "eco"].astype(str))

    def prune_noncore_files(dry_run: bool) -> int:
        removed = 0
        for eco in sorted(noncore_ecos):
            fpath = RAW_DATA_DIR / f"{eco}.json"
            if not fpath.exists():
                continue
            if dry_run:
                print(f"  [dry-run] would remove {fpath}")
            else:
                fpath.unlink()
                print(f"  removed {fpath}")
            removed += 1
        return removed

    print("\nTier counts:")
    print(f"  Tier 1: {tier1_count}")
    print(f"  Tier 2: {tier2_count}")
    print(f"  Tier 3: {tier3_count}")

    if not flags_df.empty:
        cov = flags_df["coverage_ratio"]
        print("\nCoverage ratio distribution:")
        print(
            "  "
            f"min={cov.min():.2f}, p25={cov.quantile(0.25):.2f}, "
            f"p50={cov.quantile(0.50):.2f}, p75={cov.quantile(0.75):.2f}, "
            f"max={cov.max():.2f}, mean={cov.mean():.2f}"
        )

    if dropped_from_old_tier1:
        print(
            "\nDropped from old avg-based Tier 1 (now Tier 2/3): "
            + ", ".join(sorted(set(dropped_from_old_tier1)))
        )
    else:
        print("\nDropped from old avg-based Tier 1 (now Tier 2/3): none")

    print(f"\n{changed} entries changed.")

    if changed == 0:
        print("Catalog is already up to date — no writes needed.")
        if args.dry_run:
            if args.prune_noncore:
                print("\nPruning non-core raw files:")
                removed = prune_noncore_files(dry_run=True)
                print(f"  [dry-run] total files to remove: {removed}")
            print("[dry-run] No changes written.")
            return
        flags_df.to_csv(FLAGS_PATH, index=False)
        print(f"Selection flags written → {FLAGS_PATH}")
        if args.prune_noncore:
            print("\nPruning non-core raw files:")
            removed = prune_noncore_files(dry_run=False)
            print(f"  total files removed: {removed}")
        return

    if args.dry_run:
        print("[dry-run] No changes written.")
        return

    catalog.to_csv(CATALOG_PATH, index=False)
    print(f"Catalog written → {CATALOG_PATH}")
    flags_df.to_csv(FLAGS_PATH, index=False)
    print(f"Selection flags written → {FLAGS_PATH}")
    if args.prune_noncore:
        print("\nPruning non-core raw files:")
        removed = prune_noncore_files(dry_run=False)
        print(f"  total files removed: {removed}")


if __name__ == "__main__":
    main()
