import json
import os
import subprocess
import sys
from datetime import date
from pathlib import Path

try:
    from dotenv import load_dotenv
except Exception:  # pragma: no cover
    load_dotenv = None

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


def _load_env() -> None:
    """Load environment variables from .env when python-dotenv is available."""
    if load_dotenv is None:
        return
    load_dotenv(Path(".env"))
    load_dotenv()


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


def _month_range_to(start: str, end: str) -> list[str]:
    """Return every YYYY-MM from *start* up to and including *end*."""
    sy, sm = map(int, start.split("-"))
    ey, em = map(int, end.split("-"))
    months = []
    y, m = sy, sm
    while (y, m) <= (ey, em):
        months.append(f"{y:04d}-{m:02d}")
        m += 1
        if m > 12:
            m, y = 1, y + 1
    return months


def _latest_complete_month() -> str:
    """Return the latest complete month (YYYY-MM), i.e. previous month."""
    today = date.today()
    if today.month == 1:
        return f"{today.year - 1:04d}-12"
    return f"{today.year:04d}-{today.month - 1:02d}"


def get_missing_months() -> list[str]:
    """Return complete months (YYYY-MM) not fully represented in data/raw/."""
    with open(OPENINGS_JSON) as f:
        openings = json.load(f)
    eco_codes = [o["eco"] for o in openings]
    all_months = _month_range_to(FETCH_START, _latest_complete_month())

    raw_dir = Path("data/raw")
    existing = {p.stem for p in raw_dir.glob("*.json")}  # "B20_2023-01" etc.

    missing_months = []
    for month in all_months:
        # Month is complete only when every ECO has a file
        if any(f"{eco}_{month}" not in existing for eco in eco_codes):
            missing_months.append(month)
    return missing_months


def _should_fetch_missing_data(missing: list[str]) -> bool:
    """Decide whether to fetch missing data based on config, env, or prompt."""
    if STAGES.get("fetch", False):
        return True
    if not missing:
        return False

    mode = os.environ.get("AUTO_FETCH_MISSING_DATA", "").strip().lower()
    if mode in {"1", "true", "yes", "y"}:
        print("AUTO_FETCH_MISSING_DATA enabled: fetching missing months automatically.")
        return True
    if mode in {"0", "false", "no", "n"}:
        print("AUTO_FETCH_MISSING_DATA disabled: not fetching missing months.")
        return False

    if not sys.stdin.isatty():
        print(
            "Non-interactive run detected and AUTO_FETCH_MISSING_DATA is unset; "
            "not fetching missing months. Set AUTO_FETCH_MISSING_DATA=true to auto-fetch."
        )
        return False

    first, last = missing[0], missing[-1]
    answer = input(
        f"Detected {len(missing)} missing complete month(s) in data/raw/ ({first}..{last}). "
        "Fetch now? [Y/n]: "
    ).strip().lower()
    return answer in {"", "y", "yes"}


def _run_fetch_for_missing_months(missing: list[str]) -> bool:
    """Fetch missing month range and return True if data was fetched."""
    if not missing:
        print("Fetch: all expected files present, nothing to do.")
        return False

    lichess_token = os.environ.get("LICHESS_TOKEN", "").strip()
    if not lichess_token:
        print(
            "Fetch aborted: LICHESS_TOKEN is not set. Add it to .env or export it in your shell, "
            "then run again."
        )
        return False

    first, last = missing[0], missing[-1]
    print(f"--- Stage: fetch ({len(missing)} months missing, {first}-{last}) ---")
    fetcher_bin = Path("target/debug/fetcher")
    if not fetcher_bin.exists():
        print("Building fetcher...")
        subprocess.run(["cargo", "build"], cwd="fetcher", check=True)

    try:
        subprocess.run(
            [str(fetcher_bin), "--from", first, "--to", last],
            cwd="fetcher",
            check=True,
        )
    except subprocess.CalledProcessError as exc:
        print(f"Fetch failed with exit code {exc.returncode}.")
        print(
            "If you see HTTP 401 Unauthorized, your LICHESS_TOKEN is missing, expired, or invalid. "
            "Regenerate token and retry."
        )
        return False

    return True


def _skip_or_force(path: str, label: str, force: bool) -> bool:
    """Skip existing output unless recompute is forced."""
    if force and os.path.exists(path):
        print(f"Recomputing {label}: ignoring existing {path} due to fresh fetch")
        return False
    return _skip(path, label)


def main():
    _load_env()

    missing = get_missing_months()
    fetched = False
    attempted_fetch = False
    if _should_fetch_missing_data(missing):
        attempted_fetch = True
        fetched = _run_fetch_for_missing_months(missing)

    if missing and attempted_fetch and not fetched:
        print(
            "Aborting run because fetch was requested but did not complete successfully."
        )
        return

    if missing and not fetched:
        print(
            "Warning: missing complete month data detected but fetch was skipped. "
            "Downstream outputs may be stale."
        )

    force_recompute = fetched

    if STAGES["ingest"] and not _skip_or_force(PROCESSED_CSV, "ingest", force_recompute):
        print("--- Stage: ingest ---")
        from src.ingest import ingest
        ingest()

    if STAGES["ts"] and not _skip_or_force(FORECASTS_CSV, "timeseries", force_recompute):
        print("--- Stage: timeseries ---")
        from src.timeseries import run_timeseries
        run_timeseries()

    if STAGES["engine"] and not _skip_or_force(ENGINE_CSV, "engine delta", force_recompute):
        print("--- Stage: engine delta ---")
        from src.engine_delta import run_engine_delta
        run_engine_delta()

    if STAGES["viz"] and not _skip_or_force(DASHBOARD_HTML, "visualizer", force_recompute):
        print("--- Stage: visualizer ---")
        from src.visualizer import run_visualizer
        run_visualizer()

    if STAGES["report"] and os.path.exists(FORECASTS_CSV) and os.path.exists(ENGINE_CSV):
        print("--- Stage: report ---")
        from src.report import run_report
        run_report()


if __name__ == "__main__":
    main()
