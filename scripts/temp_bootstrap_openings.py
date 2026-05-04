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
    eco_limit: int | None,
) -> tuple[list[dict[str, str]], list[str], int]:
    eligible = [r for r in rows if str(r.get("moves", "")).strip()]
    if not include_all:
        eligible = [r for r in eligible if r.get("eco", "")[0] in {"A", "B", "C", "D", "E"}]

    eligible = sorted(eligible, key=lambda r: r["eco"])
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

    active_ecos = [
        r["eco"] for r in rows
        if parse_bool(r.get("is_tracked_core", "False")) or parse_bool(r.get("is_long_tail", "False"))
    ]
    return rows, sorted(active_ecos), changed


def compute_missing_months(active_ecos: list[str], fetch_start: str) -> list[str]:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    months = month_range(fetch_start, latest_complete_month())

    # Load available months per ECO from consolidated files (one read per ECO).
    eco_month_sets: dict[str, set[str]] = {}
    for eco in active_ecos:
        eco_file = RAW_DIR / f"{eco}.json"
        if eco_file.exists():
            try:
                data = json.loads(eco_file.read_text(encoding="utf-8"))
                eco_month_sets[eco] = set(data.get("months", {}).keys())
            except Exception:
                eco_month_sets[eco] = set()
        else:
            eco_month_sets[eco] = set()

    missing = [
        m for m in months
        if any(m not in eco_month_sets[eco] for eco in active_ecos)
    ]
    return missing


def write_catalog(rows: list[dict[str, str]]) -> None:
    fields = ["eco", "name", "eco_group", "moves", "is_tracked_core", "is_long_tail", "model_tier"]
    with open(CATALOG_PATH, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)


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

    rows, active_ecos, changed = mark_active(rows, args.include_all, args.eco_limit)
    missing = compute_missing_months(active_ecos, fetch_start)

    print(f"Config fetch_start: {fetch_start}")
    print(f"Catalog rows: {len(rows)}")
    print(f"Active ECOs after bootstrap: {len(active_ecos)}")
    print(f"Rows newly marked long-tail: {changed}")
    print(f"Missing months for active set: {len(missing)}")
    if missing:
        print(f"  Range: {missing[0]} .. {missing[-1]}")

    if args.dry_run:
        print("[dry-run] No files written and no fetch started.")
        return 0

    write_catalog(rows)
    print(f"Wrote bootstrap-active catalog: {CATALOG_PATH}")

    # Sanity check the on-disk catalog before running fetcher.
    with open(CATALOG_PATH, newline="", encoding="utf-8") as f:
        disk_rows = list(csv.DictReader(f))
    disk_active = sum(
        parse_bool(r.get("is_tracked_core", "False")) or parse_bool(r.get("is_long_tail", "False"))
        for r in disk_rows
    )
    print(f"Active ECOs in written catalog: {disk_active}")

    if not args.skip_fetch and missing:
        token = os.environ.get("LICHESS_TOKEN", "").strip()
        if not token:
            raise RuntimeError("LICHESS_TOKEN is not set. Export it before --apply.")

        ensure_fetcher_built()

        env = os.environ.copy()
        if args.eco_limit is not None:
            env["OPENCAST_ECO_LIMIT"] = str(args.eco_limit)

        print("Running fetcher for missing range...")
        subprocess.run(
            [str(FETCHER_BIN), "--from", missing[0], "--to", missing[-1]],
            cwd=ROOT / "fetcher",
            env=env,
            check=True,
        )
    elif args.skip_fetch:
        print("Skipped fetch by request (--skip-fetch).")
    else:
        print("No missing months; fetch skipped.")

    print("Recomputing selection flags from raw data + config thresholds...")
    subprocess.run(["python", "scripts/compute_selection_flags.py"], cwd=ROOT, check=True)

    print("Done. Active openings now reflect your current config thresholds.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
