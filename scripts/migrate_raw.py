#!/usr/bin/env python3
"""One-shot migration: consolidate per-month raw files into per-ECO files.

Converts:
    data/raw/A00_2023-01.json, data/raw/A00_2023-02.json, ...

Into:
    data/raw/A00.json  →  {"eco": "A00", "months": {"2023-01": {...}, ...}}

After all consolidated files are written successfully, the original per-month
files are deleted.

Usage:
    python scripts/migrate_raw.py [--dry-run]
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "data" / "raw"

# Matches files like A00_2023-01.json, B12_2025-12.json
PERMONTH_RE = re.compile(r"^([A-Z]\d{2})_(\d{4}-\d{2})\.json$")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would happen without writing or deleting anything",
    )
    args = parser.parse_args()

    # 1. Glob all per-month files and group by ECO.
    eco_files: dict[str, dict[str, Path]] = {}  # {eco: {month: path}}
    for fpath in sorted(RAW_DIR.glob("*.json")):
        m = PERMONTH_RE.match(fpath.name)
        if not m:
            continue
        eco, month = m.group(1), m.group(2)
        eco_files.setdefault(eco, {})[month] = fpath

    if not eco_files:
        print("No per-month files found. Nothing to migrate.")
        return

    total_per_month = sum(len(months) for months in eco_files.values())
    print(
        f"Found {len(eco_files)} ECO(s) with {total_per_month} per-month file(s) to migrate."
    )

    if args.dry_run:
        for eco in sorted(eco_files):
            months = sorted(eco_files[eco])
            out_name = f"{eco}.json"
            print(f"  [dry-run] {eco}: {len(months)} months ({months[0]}..{months[-1]}) → {out_name}")
        print(f"\n[dry-run] Would write {len(eco_files)} consolidated file(s).")
        print(f"[dry-run] Would delete {total_per_month} per-month file(s).")
        return

    # 2. For each ECO build the consolidated structure and write atomically.
    per_month_to_delete: list[Path] = []

    for eco in sorted(eco_files):
        month_map = eco_files[eco]
        months_dict: dict[str, object] = {}

        for month in sorted(month_map):
            fpath = month_map[month]
            try:
                data = json.loads(fpath.read_text(encoding="utf-8"))
            except Exception as exc:
                print(f"  Warning: failed to read {fpath.name}: {exc} — skipping month {month}")
                continue
            months_dict[month] = data

        consolidated = {"eco": eco, "months": months_dict}
        out_path = RAW_DIR / f"{eco}.json"
        tmp_path = RAW_DIR / f"{eco}.tmp.json"

        tmp_path.write_text(json.dumps(consolidated, indent=2), encoding="utf-8")
        tmp_path.rename(out_path)

        per_month_to_delete.extend(month_map.values())
        print(f"  {eco}: {len(months_dict)} months → {out_path.name}")

    # 3. Delete per-month files only after all ECOs have been written successfully.
    for fpath in per_month_to_delete:
        fpath.unlink()

    print(
        f"\nMigration complete: {len(eco_files)} ECO(s) consolidated, "
        f"{len(per_month_to_delete)} per-month file(s) deleted."
    )


if __name__ == "__main__":
    main()
