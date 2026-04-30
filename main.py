import json
import os
import subprocess
from datetime import date, datetime
from pathlib import Path

STAGES = {
    "fetch"  : False,  # set True to re-fetch from Lichess
    "ingest" : True,
    "ts"     : True,
    "engine" : True,
    "viz"    : True,
    "report" : True,
}

PROCESSED_CSV  = "data/processed/openings_ts.csv"
FORECASTS_CSV  = "data/output/forecasts.csv"
ENGINE_CSV     = "data/output/engine_delta.csv"
DASHBOARD_HTML = "data/output/dashboard.html"
FINDINGS_MD    = "FINDINGS.md"

FETCH_START    = "2023-01"
OPENINGS_JSON  = "openings.json"


def _skip(path: str, label: str) -> bool:
    if os.path.exists(path):
        print(f"Skipping {label}: {path} already exists")
        return True
    return False


def _month_range(start: str) -> list[str]:
    """Return every YYYY-MM from *start* up to and including the current month."""
    sy, sm = map(int, start.split("-"))
    today = date.today()
    months = []
    y, m = sy, sm
    while (y, m) <= (today.year, today.month):
        months.append(f"{y:04d}-{m:02d}")
        m += 1
        if m > 12:
            m, y = 1, y + 1
    return months


def get_missing_months() -> list[str]:
    """Return month strings (YYYY-MM) not fully represented in data/raw/."""
    with open(OPENINGS_JSON) as f:
        openings = json.load(f)
    eco_codes = [o["eco"] for o in openings]
    all_months = _month_range(FETCH_START)

    raw_dir = Path("data/raw")
    existing = {p.stem for p in raw_dir.glob("*.json")}  # "B20_2023-01" etc.

    missing_months = []
    for month in all_months:
        # Month is complete only when every ECO has a file
        if any(f"{eco}_{month}" not in existing for eco in eco_codes):
            missing_months.append(month)
    return missing_months


def main():
    if STAGES["fetch"]:
        missing = get_missing_months()
        if missing:
            first, last = missing[0], missing[-1]
            print(f"--- Stage: fetch ({len(missing)} months missing, {first}–{last}) ---")
            fetcher_bin = Path("fetcher/target/debug/fetcher")
            if not fetcher_bin.exists():
                print("Building fetcher…")
                subprocess.run(["cargo", "build"], cwd="fetcher", check=True)
            subprocess.run(
                [str(fetcher_bin), "--from", first, "--to", last],
                check=True,
            )
        else:
            print("Fetch: all expected files present, nothing to do.")

    if STAGES["ingest"] and not _skip(PROCESSED_CSV, "ingest"):
        print("--- Stage: ingest ---")
        from src.ingest import ingest
        ingest()

    if STAGES["ts"] and not _skip(FORECASTS_CSV, "timeseries"):
        print("--- Stage: timeseries ---")
        from src.timeseries import run_timeseries
        run_timeseries()

    if STAGES["engine"] and not _skip(ENGINE_CSV, "engine delta"):
        print("--- Stage: engine delta ---")
        from src.engine_delta import run_engine_delta
        run_engine_delta()

    if STAGES["viz"] and not _skip(DASHBOARD_HTML, "visualizer"):
        print("--- Stage: visualizer ---")
        from src.visualizer import run_visualizer
        run_visualizer()

    if STAGES["report"] and os.path.exists(FORECASTS_CSV) and os.path.exists(ENGINE_CSV):
        print("--- Stage: report ---")
        from src.report import run_report
        run_report()


if __name__ == "__main__":
    main()
