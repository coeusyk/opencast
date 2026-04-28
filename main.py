import os

STAGES = {
    "fetch"  : False,  # set True to re-fetch from Lichess
    "ingest" : True,
    "ts"     : True,
    "engine" : True,
    "viz"    : True,
}

PROCESSED_CSV  = "data/processed/openings_ts.csv"
FORECASTS_CSV  = "data/output/forecasts.csv"
ENGINE_CSV     = "data/output/engine_delta.csv"
DASHBOARD_HTML = "data/output/dashboard.html"


def _skip(path: str, label: str) -> bool:
    if os.path.exists(path):
        print(f"Skipping {label}: {path} already exists")
        return True
    return False


def main():
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


if __name__ == "__main__":
    main()
