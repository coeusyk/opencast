import json
import os
import shutil
from pathlib import Path

import pandas as pd

from .data_access import (
    ASSETS_DIR,
    CATALOG_CSV,
    ENGINE_CSV,
    ICON_SOURCE_PNG,
    LONG_TAIL_CSV,
    MOVE_STATS_CSV,
    OPENING_LINES_JSON,
    OUTPUT_DIR,
    _load_findings_json,
    _load_narratives_json,
    _safe_read_forecasts,
    _serialize_openings_data,
)
from .pages.families import render_families
from .pages.opening_template import render_opening_template
from .pages.openings import render_openings_table
from .pages.overview import render_overview
from ..report import _forecast_directions


def run_visualizer() -> None:
    os.makedirs(ASSETS_DIR, exist_ok=True)

    forecasts = _safe_read_forecasts()
    engine_df = pd.read_csv(ENGINE_CSV) if os.path.exists(ENGINE_CSV) else pd.DataFrame()
    catalog = pd.read_csv(CATALOG_CSV) if os.path.exists(CATALOG_CSV) else pd.DataFrame()
    findings = _load_findings_json()
    narratives = _load_narratives_json()
    try:
        long_tail_df = pd.read_csv(LONG_TAIL_CSV) if os.path.exists(LONG_TAIL_CSV) else pd.DataFrame()
    except Exception:
        long_tail_df = pd.DataFrame()
    try:
        move_stats_df = pd.read_csv(MOVE_STATS_CSV) if os.path.exists(MOVE_STATS_CSV) else pd.DataFrame()
    except Exception:
        move_stats_df = pd.DataFrame()

    assets_root = Path(__file__).resolve().parent.parent / "assets"
    for asset_name in (
        "shared.css",
        "nav.js",
        "opening.js",
        "jquery-3.7.1.min.js",
        "chess-0.10.3.min.js",
        "chessboard-1.0.0.min.js",
        "chessboard-1.0.0.min.css",
    ):
        src = assets_root / asset_name
        if not src.exists():
            src = assets_root / "vendor" / asset_name
        dst = Path(ASSETS_DIR) / asset_name
        if src.exists():
            shutil.copy2(src, dst)

    icon_src = Path(ICON_SOURCE_PNG)
    icon_dst = Path(ASSETS_DIR) / "opencast_icon.png"
    if icon_src.exists():
        shutil.copy2(icon_src, icon_dst)
    elif not icon_dst.exists():
        print(f"Warning: icon source not found at {icon_src} and no existing asset to use")

    chesspieces_src = assets_root / "chesspieces"
    chesspieces_dst = Path(ASSETS_DIR) / "chesspieces"
    if chesspieces_src.exists() and chesspieces_src.is_dir():
        if chesspieces_dst.exists():
            shutil.rmtree(chesspieces_dst)
        shutil.copytree(chesspieces_src, chesspieces_dst)

    opening_lines_src = Path(OPENING_LINES_JSON)
    opening_lines_dst = Path(ASSETS_DIR) / "opening_lines.json"
    if opening_lines_src.exists():
        shutil.copy2(opening_lines_src, opening_lines_dst)
        print(f"Opening lines written -> {opening_lines_dst}")
    else:
        print(f"Warning: opening lines source not found at {opening_lines_src}")

    _, trend_signals = _forecast_directions(forecasts)
    openings_data = _serialize_openings_data(
        forecasts,
        engine_df,
        catalog,
        findings,
        narratives,
        long_tail_df,
        move_stats_df,
        trend_signals=trend_signals,
    )

    overview_html = render_overview(
        forecasts,
        engine_df,
        findings,
        trend_signals=trend_signals,
        openings_data=openings_data,
    )
    overview_path = os.path.join(OUTPUT_DIR, "index.html")
    Path(overview_path).write_text(overview_html, encoding="utf-8")
    print(f"Overview written -> {overview_path}")

    if not catalog.empty:
        openings_html = render_openings_table(forecasts, engine_df, catalog)
        openings_path = os.path.join(OUTPUT_DIR, "openings.html")
        Path(openings_path).write_text(openings_html, encoding="utf-8")
        print(f"Openings table written -> {openings_path}")

    openings_data_path = os.path.join(ASSETS_DIR, "openings_data.json")
    Path(openings_data_path).write_text(json.dumps(openings_data, indent=2), encoding="utf-8")
    print(f"Openings data written -> {openings_data_path}")

    opening_template_html = render_opening_template()
    opening_template_path = os.path.join(OUTPUT_DIR, "opening.html")
    Path(opening_template_path).write_text(opening_template_html, encoding="utf-8")
    print(f"Opening template written -> {opening_template_path}")

    for stale_file in Path(OUTPUT_DIR).glob("opening_*.html"):
        stale_file.unlink(missing_ok=True)
    stale_dir = Path(OUTPUT_DIR) / "opening"
    if stale_dir.exists() and stale_dir.is_dir():
        shutil.rmtree(stale_dir)

    families_html = render_families(forecasts, engine_df=engine_df, catalog=catalog, openings_data=openings_data)
    families_path = os.path.join(OUTPUT_DIR, "families.html")
    Path(families_path).write_text(families_html, encoding="utf-8")
    print(f"Families page written -> {families_path}")

    print(f"\nDashboard written -> {OUTPUT_DIR}/ ({len(openings_data)} ECOs)")