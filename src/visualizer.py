"""Public compatibility shim for dashboard rendering."""

from .dashboard.builder import run_visualizer
from .dashboard.data_access import (
	ASSETS_DIR,
	CATALOG_CSV,
	CONFIG_JSON,
	ENGINE_CSV,
	FINDINGS_JSON,
	FORECASTS_CSV,
	ICON_SOURCE_PNG,
	LONG_TAIL_CSV,
	MOVE_STATS_CSV,
	NARRATIVES_JSON,
	OPENING_LINES_JSON,
	OUTPUT_DIR,
	_load_findings_json,
	_load_narratives_json,
	_load_runtime_config,
	_safe_read_forecasts,
	_serialize_openings_data,
	_top_lines_for_opening,
)
from .dashboard.pages.families import render_families, render_families_page
from .dashboard.pages.opening_template import render_opening_template
from .dashboard.pages.openings import render_openings_page, render_openings_table
from .dashboard.pages.overview import render_overview