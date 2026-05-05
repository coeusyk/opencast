#!/usr/bin/env python3
"""Temporary bootstrap utility to expand openings beyond the current 20.

Why this exists:
- Fetch only pulls openings marked active in data/openings_catalog.csv
  (is_tracked_core OR is_long_tail).
- If only 20 openings are active, no new openings can ever be fetched.

What this script does:
1) Temporarily marks additional catalog rows as active (long-tail).
2) Computes missing months from config.json fetch_start to latest complete month.
3) Runs fetcher for the missing range.
4) Re-applies threshold rules via scripts/compute_selection_flags.py so the final
   active set matches config criteria.

Usage examples:
  python scripts/temp_bootstrap_openings.py --dry-run
  python scripts/temp_bootstrap_openings.py --apply --eco-limit 120
  python scripts/temp_bootstrap_openings.py --apply --include-all
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import subprocess
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CATALOG_PATH = ROOT / "data" / "openings_catalog.csv"
RAW_DIR = ROOT / "data" / "raw"
CONFIG_PATH = ROOT / "config.json"
FETCHER_BIN = ROOT / "fetcher" / "target" / "debug" / "fetcher"
FETCHER_SRC = ROOT / "fetcher" / "src" / "main.rs"


def month_range(start: str, end: str) -> list[str]:
    sy, sm = map(int, start.split("-"))
    ey, em = map(int, end.split("-"))
    out = []
    y, m = sy, sm
    while (y, m) <= (ey, em):
        out.append(f"{y:04d}-{m:02d}")
        m += 1
        if m > 12:
            m = 1
            y += 1
    return out


def latest_complete_month() -> str:
    today = date.today()
    if today.month == 1:
        return f"{today.year - 1:04d}-12"
    return f"{today.year:04d}-{today.month - 1:02d}"


def load_config() -> dict:
    with open(CONFIG_PATH, encoding="utf-8") as f:
        return json.load(f)


def parse_bool(s: str) -> bool:
    return str(s).strip().lower() == "true"


def mark_active(
    rows: list[dict[str, str]],
    include_all: bool,
    eco_offset: int | None,
    eco_limit: int | None,
) -> tuple[list[dict[str, str]], list[str], int]:
    eligible = [r for r in rows if str(r.get("moves", "")).strip()]
    if not include_all:
        eligible = [r for r in eligible if r.get("eco", "")[0] in {"A", "B", "C", "D", "E"}]

    eligible = sorted(eligible, key=lambda r: r["eco"])
    if eco_offset is not None and eco_offset > 0:
        eligible = eligible[eco_offset:]
    if eco_limit is not None:
        eligible = eligible[:eco_limit]

    selected = {r["eco"] for r in eligible}
    changed = 0

    for r in rows:
        eco = r.get("eco", "")
        core = parse_bool(r.get("is_tracked_core", "False"))
        tail = parse_bool(r.get("is_long_tail", "False"))

        if eco in selected and not core and not tail:
            r["is_long_tail"] = "True"
            r["model_tier"] = "3"
            changed += 1

    return rows, sorted(selected), changed


def compute_missing_months(
    active_ecos: list[str],
    fetch_start: str,
    forced_complete: set[str] | None = None,
) -> tuple[list[str], list[str], dict[str, list[str]]]:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    months = month_range(fetch_start, latest_complete_month())
    forced_complete = forced_complete or set()

    # Load available months per ECO from consolidated files (one read per ECO).
    eco_month_sets: dict[str, set[str]] = {}
    for eco in active_ecos:
        eco_file = RAW_DIR / f"{eco}.json"
        if eco_file.exists():
            try:
                data = json.loads(eco_file.read_text(encoding="utf-8"))
                present = set(data.get("months", {}).keys())
                skipped = set(data.get("_meta", {}).get("skipped_months", {}).keys())
                eco_month_sets[eco] = present | skipped
            except Exception:
                eco_month_sets[eco] = set()
        else:
            eco_month_sets[eco] = set()

    missing_by_eco: dict[str, list[str]] = {}
    complete_ecos: list[str] = []
    for eco in active_ecos:
        if eco in forced_complete:
            complete_ecos.append(eco)
            continue
        missing_for_eco = [m for m in months if m not in eco_month_sets[eco]]
        if missing_for_eco:
            missing_by_eco[eco] = missing_for_eco
        else:
            complete_ecos.append(eco)

    missing = sorted({m for ms in missing_by_eco.values() for m in ms})
    return missing, sorted(complete_ecos), missing_by_eco


def write_catalog(rows: list[dict[str, str]]) -> None:
    base_fields = ["eco", "name", "eco_group", "moves", "is_tracked_core", "is_long_tail", "model_tier"]
    extra_fields: list[str] = []
    for r in rows:
        for k in r.keys():
            if k not in base_fields and k not in extra_fields:
                extra_fields.append(k)
    fields = base_fields + extra_fields
    with open(CATALOG_PATH, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)


def update_fetch_tracking(
    rows: list[dict[str, str]],
    target_ecos: list[str],
    complete_ecos: list[str],
    latest_month: str,
    status_by_eco: dict[str, str] | None = None,
) -> None:
    target_set = set(target_ecos)
    complete_set = set(complete_ecos)
    status_by_eco = status_by_eco or {}
    for r in rows:
        eco = r.get("eco", "")
        if eco not in target_set:
            continue
        if eco in status_by_eco:
            r["bootstrap_fetch_status"] = status_by_eco[eco]
        is_complete = eco in complete_set
        r["bootstrap_fetch_complete"] = "True" if is_complete else "False"
        r["bootstrap_fetched_until"] = latest_month if is_complete else ""


def is_terminal_status(status: str) -> bool:
    return status == "no_file" or status == "pruned_empty" or status.startswith("pruned_tier3")


def month_total_games(month_data: dict) -> int:
    return int(month_data.get("white", 0)) + int(month_data.get("draws", 0)) + int(month_data.get("black", 0))


def classify_and_prune_eco(eco: str, expected_months: list[str], cfg: dict) -> str:
    eco_file = RAW_DIR / f"{eco}.json"
    if not eco_file.exists():
        return "no_file"

    try:
        payload = json.loads(eco_file.read_text(encoding="utf-8"))
    except Exception:
        return "invalid_json"

    months_data = payload.get("months", {})
    if not isinstance(months_data, dict) or not months_data:
        eco_file.unlink(missing_ok=True)
        return "pruned_empty"

    min_games = int(cfg.get("min_monthly_games", 0))
    min_months = int(cfg.get("min_months_data", 24))
    cov_t1 = float(cfg.get("min_coverage_ratio", 0.75))
    cov_t2 = float(cfg.get("min_coverage_ratio_tier2", 0.4))

    qualifying_months = 0
    for month in expected_months:
        month_payload = months_data.get(month)
        if isinstance(month_payload, dict) and month_total_games(month_payload) >= min_games:
            qualifying_months += 1

    total_months = len(expected_months)
    coverage_ratio = (qualifying_months / total_months) if total_months else 0.0

    if total_months < min_months or coverage_ratio < cov_t2:
        eco_file.unlink(missing_ok=True)
        return f"pruned_tier3({qualifying_months}/{total_months},{coverage_ratio:.3f})"
    if coverage_ratio < cov_t1:
        return f"tier2({qualifying_months}/{total_months},{coverage_ratio:.3f})"
    return f"tier1({qualifying_months}/{total_months},{coverage_ratio:.3f})"


def remove_bad_raw_files() -> tuple[list[str], list[str]]:
    removed_empty: list[str] = []
    removed_below_min: list[str] = []

    for eco_file in sorted(RAW_DIR.glob("*.json")):
        try:
            payload = json.loads(eco_file.read_text(encoding="utf-8"))
        except Exception:
            continue

        months_data = payload.get("months", {})
        skipped = payload.get("_meta", {}).get("skipped_months", {})
        has_below_min = isinstance(skipped, dict) and any(v == "below_min_games" for v in skipped.values())

        if not isinstance(months_data, dict) or not months_data:
            eco_file.unlink(missing_ok=True)
            removed_empty.append(eco_file.name)
            continue

        if has_below_min:
            eco_file.unlink(missing_ok=True)
            removed_below_min.append(eco_file.name)

    return removed_empty, removed_below_min


def ensure_fetcher_built() -> None:
    """Build fetcher when missing or older than source files."""
    rebuild = False
    reason = ""

    if not FETCHER_BIN.exists():
        rebuild = True
        reason = "binary missing"
    else:
        bin_mtime = FETCHER_BIN.stat().st_mtime
        # Rebuild when main source is newer than binary.
        if FETCHER_SRC.exists() and FETCHER_SRC.stat().st_mtime > bin_mtime:
            rebuild = True
            reason = "source newer than binary"

    if rebuild:
        print(f"Building fetcher ({reason})...")
        subprocess.run(["cargo", "build"], cwd=ROOT / "fetcher", check=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Write changes and run fetch + flag recompute")
    parser.add_argument("--dry-run", action="store_true", help="Preview only")
    parser.add_argument("--include-all", action="store_true", help="Activate all catalog rows with moves")
    parser.add_argument("--eco-offset", type=int, default=0, help="Skip the first N ECOs after sorting")
    parser.add_argument("--eco-limit", type=int, default=None, help="Only activate the first N ECOs (sorted)")
    parser.add_argument("--skip-fetch", action="store_true", help="Only update flags in catalog, do not fetch")
    args = parser.parse_args()

    if not CATALOG_PATH.exists():
        raise FileNotFoundError(f"Missing catalog: {CATALOG_PATH}")

    if args.apply and args.dry_run:
        raise ValueError("Use either --apply or --dry-run, not both")
    if not args.apply and not args.dry_run:
        args.dry_run = True

    cfg = load_config()
    fetch_start = str(cfg.get("fetch_start", "2023-01"))

    with open(CATALOG_PATH, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    rows, target_ecos, changed = mark_active(rows, args.include_all, args.eco_offset, args.eco_limit)
    active_ecos = [
        r["eco"] for r in rows
        if parse_bool(r.get("is_tracked_core", "False")) or parse_bool(r.get("is_long_tail", "False"))
    ]
    pre_marked_complete = {
        r["eco"]
        for r in rows
        if r.get("eco", "") in set(target_ecos)
        and parse_bool(r.get("bootstrap_fetch_complete", "False"))
    }
    latest_month = latest_complete_month()
    missing, complete_ecos, missing_by_eco = compute_missing_months(
        target_ecos,
        fetch_start,
        forced_complete=pre_marked_complete,
    )
    fetch_target_ecos = sorted(missing_by_eco.keys())
    update_fetch_tracking(rows, target_ecos, complete_ecos, latest_month)

    print(f"Config fetch_start: {fetch_start}")
    print(f"Catalog rows: {len(rows)}")
    print(f"Selected ECOs in this batch: {len(target_ecos)}")
    print(f"Active ECOs after bootstrap: {len(active_ecos)}")
    print(f"Rows newly marked long-tail: {changed}")
    print(f"Selected ECOs already complete: {len(complete_ecos)}")
    print(f"Selected ECOs still missing months: {len(fetch_target_ecos)}")
    print(f"Missing months for selected set: {len(missing)}")
    if missing:
        print(f"  Range: {missing[0]} .. {missing[-1]}")

    if args.dry_run:
        print("[dry-run] No files written and no fetch started.")
        return 0

    write_catalog(rows)
    print(f"Wrote bootstrap-active catalog: {CATALOG_PATH}")

    removed_empty, removed_below_min = remove_bad_raw_files()
    if removed_empty or removed_below_min:
        print(
            "Removed bad raw files: "
            f"empty={len(removed_empty)}, below_min_games={len(removed_below_min)}"
        )

    # Sanity check the on-disk catalog before running fetcher.
    with open(CATALOG_PATH, newline="", encoding="utf-8") as f:
        disk_rows = list(csv.DictReader(f))
    disk_active = sum(
        parse_bool(r.get("is_tracked_core", "False")) or parse_bool(r.get("is_long_tail", "False"))
        for r in disk_rows
    )
    print(f"Active ECOs in written catalog: {disk_active}")

    if not args.skip_fetch and fetch_target_ecos:
        token = os.environ.get("LICHESS_TOKEN", "").strip()
        if not token:
            raise RuntimeError("LICHESS_TOKEN is not set. Export it before --apply.")

        ensure_fetcher_built()

        env_base = os.environ.copy()

        min_games = cfg.get("min_monthly_games", 0)
        expected_months = month_range(fetch_start, latest_month)
        status_by_eco: dict[str, str] = {}
        terminal_done_ecos: set[str] = set()
        print(
            "Running fetcher ECO-by-ECO for selected batch "
            f"(min-games={min_games}, target-ecos={len(fetch_target_ecos)})..."
        )

        for idx, eco in enumerate(fetch_target_ecos, start=1):
            eco_missing = missing_by_eco.get(eco, [])
            if not eco_missing:
                continue
            env = env_base.copy()
            env["OPENCAST_ECO_ONLY"] = eco
            print(f"[{idx}/{len(fetch_target_ecos)}] Fetching {eco} ({eco_missing[0]}..{eco_missing[-1]})")
            subprocess.run(
                [str(FETCHER_BIN), "--from", eco_missing[0], "--to", eco_missing[-1],
                 "--min-games", str(min_games)],
                cwd=ROOT / "fetcher",
                env=env,
                check=True,
            )
            status = classify_and_prune_eco(eco, expected_months, cfg)
            status_by_eco[eco] = status
            if is_terminal_status(status):
                terminal_done_ecos.add(eco)
                # Persist terminal completion immediately so interrupted runs do not refetch these ECOs.
                update_fetch_tracking(
                    rows,
                    target_ecos,
                    complete_ecos + sorted(terminal_done_ecos),
                    latest_month,
                    status_by_eco,
                )
                write_catalog(rows)
            print(f"  -> {eco}: {status}")
    elif args.skip_fetch:
        print("Skipped fetch by request (--skip-fetch).")
    else:
        print("No missing months; fetch skipped.")

    # Recompute completion state after fetch and persist in catalog.
    missing, complete_ecos, _ = compute_missing_months(
        target_ecos,
        fetch_start,
        forced_complete=pre_marked_complete,
    )
    final_complete = set(complete_ecos)
    for r in rows:
        eco = r.get("eco", "")
        if eco in set(target_ecos) and is_terminal_status(r.get("bootstrap_fetch_status", "")):
            final_complete.add(eco)
    update_fetch_tracking(rows, target_ecos, sorted(final_complete), latest_month)
    write_catalog(rows)

    print("Recomputing selection flags + pruning below-threshold months/non-core files...")
    subprocess.run(
        [
            "python",
            "scripts/compute_selection_flags.py",
            "--prune-below-threshold-months",
            "--prune-noncore",
        ],
        cwd=ROOT,
        check=True,
    )

    print("Done. Active openings now reflect your current config thresholds.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
