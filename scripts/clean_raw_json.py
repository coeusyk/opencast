import argparse
import json
from pathlib import Path
from typing import Any


TARGET_KEYS = {"recentGames", "topGames"}


def remove_target_keys(node: Any) -> int:
    removed = 0

    if isinstance(node, dict):
        for key in list(node.keys()):
            if key in TARGET_KEYS:
                del node[key]
                removed += 1
            else:
                removed += remove_target_keys(node[key])
    elif isinstance(node, list):
        for item in node:
            removed += remove_target_keys(item)

    return removed


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Remove recentGames/topGames noise from data/raw JSON files."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print planned changes without writing files.",
    )
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parent.parent
    raw_root = repo_root / "data" / "raw"

    total_files_scanned = 0
    total_files_cleaned = 0
    total_keys_removed = 0

    for file_path in sorted(raw_root.rglob("*.json")):
        total_files_scanned += 1

        with file_path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)

        removed = remove_target_keys(payload)
        if removed == 0:
            print(f"skipped: {file_path}")
            continue

        total_files_cleaned += 1
        total_keys_removed += removed

        if args.dry_run:
            print(f"cleaned: {file_path} removed {removed} keys")
            continue

        with file_path.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, separators=(",", ":"))

        print(f"cleaned: {file_path} removed {removed} keys")

    print(
        "summary: "
        f"total files scanned={total_files_scanned}, "
        f"total files cleaned={total_files_cleaned}, "
        f"total keys removed={total_keys_removed}"
    )


if __name__ == "__main__":
    main()