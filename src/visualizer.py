import json
import os
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go

_HERE = os.path.dirname(__file__)
FORECASTS_CSV = os.path.join(_HERE, "..", "data", "output", "forecasts.csv")
ENGINE_CSV = os.path.join(_HERE, "..", "data", "output", "engine_delta.csv")
CATALOG_CSV = os.path.join(_HERE, "..", "data", "openings_catalog.csv")
FINDINGS_JSON   = os.path.join(_HERE, "..", "findings", "findings.json")
NARRATIVES_JSON = os.path.join(_HERE, "..", "findings", "narratives.json")
LONG_TAIL_CSV   = os.path.join(_HERE, "..", "data", "output", "long_tail_stats.csv")
MOVE_STATS_CSV  = os.path.join(_HERE, "..", "data", "output", "move_stats.csv")
OUTPUT_DIR = os.path.join(_HERE, "..", "data", "output", "dashboard")
ASSETS_DIR = os.path.join(OUTPUT_DIR, "assets")

# -- Design tokens -------------------------------------------------------------
PANEL_BG = "#0e0e0f"
GRID_COLOR = "rgba(255, 255, 255, 0.06)"
TEXT_PRIMARY = "#ededee"
TEXT_SECONDARY = "#8b8b8f"
ACCENT = "#57C7FF"
ECO_COLORS = {"A": "#7CC7FF", "B": "#7BE495", "C": "#F6C177", "D": "#F28DA6", "E": "#B9A5FF"}
BODY_FONT    = "'Inter', system-ui, sans-serif"
DISPLAY_FONT = "'Instrument Serif', Georgia, serif"

FORECAST_COLUMNS = [
    "eco",
    "opening_name",
    "month",
    "actual",
    "forecast",
    "lower_ci",
    "upper_ci",
    "is_forecast",
    "structural_break",
    "model_tier",
]

LINE_COLORS = ["#57C7FF", "#7BE495", "#F6C177", "#F28DA6", "#B9A5FF"]


# -- Private helpers -----------------------------------------------------------
def _hex_to_rgba(hex_color: str, alpha: float = 0.12) -> str:
    """Convert hex color (e.g., '#57C7FF') to RGBA string (e.g., 'rgba(87, 199, 255, 0.12)')."""
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f"rgba({r}, {g}, {b}, {alpha})"


def _apply_plotly_typography(fig: go.Figure, title_size: int) -> None:
    fig.update_layout(
        font=dict(family=BODY_FONT, color=TEXT_PRIMARY),
        title_font=dict(family=DISPLAY_FONT, size=title_size, color=TEXT_PRIMARY),
        plot_bgcolor=PANEL_BG,
        paper_bgcolor=PANEL_BG,
    )
    fig.update_xaxes(
        gridcolor=GRID_COLOR,
        zerolinecolor=GRID_COLOR,
        tickfont=dict(color=TEXT_SECONDARY),
    )
    fig.update_yaxes(
        gridcolor=GRID_COLOR,
        zerolinecolor=GRID_COLOR,
        tickfont=dict(color=TEXT_SECONDARY),
    )


def _safe_read_forecasts() -> pd.DataFrame:
    try:
        df = pd.read_csv(FORECASTS_CSV)
    except Exception:
        return pd.DataFrame(columns=FORECAST_COLUMNS)

    for col in FORECAST_COLUMNS:
        if col not in df.columns:
            df[col] = None
    return df


def _reps_by_max_delta(engine_df: pd.DataFrame) -> list[str]:
    """Pick one ECO per group (A–E) with the highest absolute engine delta."""
    if engine_df.empty or "delta" not in engine_df.columns:
        return []
    df = engine_df.copy()
    df["group"] = df["eco"].str[0]
    reps = (
        df.assign(abs_delta=df["delta"].abs())
        .sort_values("abs_delta", ascending=False)
        .groupby("group")
        .first()
        .reset_index()["eco"]
        .tolist()
    )
    return reps


def _build_panel1_figure(forecasts: pd.DataFrame, engine_df: pd.DataFrame) -> go.Figure:
    fig = go.Figure()
    top_ecos = _reps_by_max_delta(engine_df)
    all_break_months: set = set()

    for eco, color in zip(top_ecos, LINE_COLORS):
        grp = forecasts[forecasts["eco"] == eco].copy()
        if grp.empty:
            continue

        grp["month"] = pd.to_datetime(grp["month"])
        grp = grp.sort_values("month")
        actuals = grp[grp["is_forecast"] == False]
        fc_rows = grp[grp["is_forecast"] == True]

        fig.add_trace(
            go.Scatter(
                x=actuals["month"],
                y=actuals["actual"],
                name=eco,
                mode="lines",
                line=dict(color=color, width=2),
            )
        )

        if not fc_rows.empty:
            fig.add_trace(
                go.Scatter(
                    x=fc_rows["month"],
                    y=fc_rows["forecast"],
                    name=f"{eco} forecast",
                    mode="lines",
                    line=dict(color=color, dash="dash", width=1.5),
                    showlegend=False,
                )
            )
            fig.add_trace(
                go.Scatter(
                    x=pd.concat([fc_rows["month"], fc_rows["month"].iloc[::-1]]),
                    y=pd.concat([fc_rows["upper_ci"], fc_rows["lower_ci"].iloc[::-1]]),
                    fill="toself",
                    fillcolor=_hex_to_rgba(color),
                    line=dict(color="rgba(0,0,0,0)"),
                    showlegend=False,
                    name=f"{eco} CI",
                )
            )

        breaks = actuals[actuals["structural_break"] == True]["month"]
        for brk in breaks:
            all_break_months.add(brk)

    if all_break_months:
        for brk in sorted(all_break_months)[-3:]:
            fig.add_vline(
                x=brk.timestamp() * 1000,
                line=dict(color="rgba(255,255,255,0.15)", dash="dot", width=1),
            )

    fig.update_layout(
        title="Win Rate Forecast by Opening",
        xaxis_title="Month",
        yaxis_title="White Win Rate",
    )
    _apply_plotly_typography(fig, title_size=16)
    return fig


def _build_panel2_figure(engine_df: pd.DataFrame) -> go.Figure:
    fig = go.Figure()
    if engine_df.empty:
        _apply_plotly_typography(fig, title_size=16)
        return fig

    top5_ecos = set(
        engine_df.reindex(engine_df["delta"].abs().nlargest(5).index)["eco"].tolist()
        if "delta" in engine_df.columns else []
    )

    for eco_cat, color in ECO_COLORS.items():
        sub = engine_df[engine_df["eco"].str.startswith(eco_cat)].copy()
        if sub.empty:
            continue

        bg = sub[~sub["eco"].isin(top5_ecos)]
        hl = sub[sub["eco"].isin(top5_ecos)]

        if not bg.empty:
            fig.add_trace(
                go.Scatter(
                    x=bg["engine_cp"],
                    y=bg["human_win_rate_2000"],
                    mode="markers",
                    name=f"ECO {eco_cat}",
                    text=bg["eco"],
                    marker=dict(color=color, size=8, opacity=0.35, line=dict(width=0)),
                    hovertemplate="<b>%{text}</b><br>Engine cp: %{x}<br>Win rate: %{y:.3f}<br><extra></extra>",
                    showlegend=True,
                )
            )

        if not hl.empty:
            fig.add_trace(
                go.Scatter(
                    x=hl["engine_cp"],
                    y=hl["human_win_rate_2000"],
                    mode="markers+text",
                    name=f"ECO {eco_cat} (outlier)",
                    text=hl["eco"],
                    textposition="top center",
                    marker=dict(color=color, size=11, opacity=1.0, line=dict(width=1, color=PANEL_BG)),
                    hovertemplate="<b>%{text}</b><br>Engine cp: %{x}<br>Win rate: %{y:.3f}<br><extra></extra>",
                    showlegend=False,
                )
            )

    cp_range = list(range(-300, 301, 10))
    ref_probs = [1.0 / (1.0 + 10 ** (-cp / 400)) for cp in cp_range]
    fig.add_trace(
        go.Scatter(
            x=cp_range,
            y=ref_probs,
            mode="lines",
            name="Engine expected",
            line=dict(color=TEXT_SECONDARY, dash="dash", width=1),
        )
    )

    # Quadrant dividers
    fig.add_hline(y=0.5, line=dict(color=GRID_COLOR, width=1, dash="dot"))
    fig.add_vline(x=0, line=dict(color=GRID_COLOR, width=1, dash="dot"))

    # Quadrant annotations
    _quadrants = [
        (-220, 0.537, "Humans overperform<br><i>practical play favoured</i>"),
        ( 220, 0.537, "Engine strength<br><i>well executed</i>"),
        (-220, 0.463, "Objectively weak<br><i>& underplayed</i>"),
        ( 220, 0.463, "Theory-dependent<br><i>advantage lost in play</i>"),
    ]
    for qx, qy, qtxt in _quadrants:
        fig.add_annotation(
            x=qx, y=qy,
            text=qtxt,
            showarrow=False,
            font=dict(color=TEXT_SECONDARY, size=9, family=BODY_FONT),
            opacity=0.55,
            align="center",
        )

    fig.update_layout(
        title="Engine Delta: Human vs Engine Win Rate",
        xaxis_title="Engine centipawn score",
        yaxis_title="Human win rate (2000+)",
    )
    _apply_plotly_typography(fig, title_size=16)
    return fig


def _build_panel3_figure(engine_df: pd.DataFrame) -> go.Figure:
    """Bar chart of avg human win rate per ECO family (A–E)."""
    fig = go.Figure()
    if engine_df.empty or "human_win_rate_2000" not in engine_df.columns:
        _apply_plotly_typography(fig, title_size=16)
        return fig

    df = engine_df.copy()
    df["group"] = df["eco"].str[0]
    group_avg = df.groupby("group")["human_win_rate_2000"].mean()
    colors = [ECO_COLORS.get(g, TEXT_SECONDARY) for g in group_avg.index]

    fig.add_trace(
        go.Bar(
            x=list(group_avg.index),
            y=list(group_avg.values),
            marker_color=colors,
            text=[f"{v:.3f}" for v in group_avg.values],
            textposition="outside",
            textfont=dict(color=TEXT_PRIMARY),
            hovertemplate="ECO %{x}<br>Avg win rate: %{y:.4f}<extra></extra>",
        )
    )

    fig.add_hline(
        y=0.5,
        line=dict(color=TEXT_SECONDARY, dash="dash", width=1),
        annotation_text="50 %",
        annotation_font=dict(color=TEXT_SECONDARY, size=10),
    )

    fig.update_layout(
        title="Average Human Win Rate by ECO Family",
        xaxis_title="ECO Family",
        yaxis_title="Avg White Win Rate (2000+)",
        yaxis=dict(range=[0.46, 0.54]),
        bargap=0.4,
    )
    _apply_plotly_typography(fig, title_size=16)
    return fig


def _load_findings_json() -> dict | None:
    try:
        with open(FINDINGS_JSON, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _load_narratives_json() -> dict:
    """Load findings/narratives.json, returning empty structure on failure."""
    try:
        with open(NARRATIVES_JSON, encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict) or "per_opening" not in data:
            return {"per_opening": {}}
        return data
    except Exception:
        return {"per_opening": {}}


def _top_lines_for_opening(move_stats_df: pd.DataFrame | None, eco: str, limit: int = 3) -> list[dict]:
    """Return top move lines driving the current month's opening behavior."""
    if move_stats_df is None or move_stats_df.empty or "eco" not in move_stats_df.columns:
        return []

    sub = move_stats_df[move_stats_df["eco"].astype(str) == str(eco)].copy()
    if sub.empty or "month" not in sub.columns:
        return []

    latest_month = str(sub["month"].astype(str).max())
    latest = sub[sub["month"].astype(str) == latest_month].copy()
    if latest.empty:
        return []

    for col in ("games", "white_win_rate", "share_of_games", "delta_share_12m", "delta_wr_12m"):
        if col not in latest.columns:
            latest[col] = None

    latest["games"] = pd.to_numeric(latest["games"], errors="coerce").fillna(0)
    latest["white_win_rate"] = pd.to_numeric(latest["white_win_rate"], errors="coerce")
    latest["share_of_games"] = pd.to_numeric(latest["share_of_games"], errors="coerce").fillna(0.0)
    latest["delta_share_12m"] = pd.to_numeric(latest["delta_share_12m"], errors="coerce")
    latest["delta_wr_12m"] = pd.to_numeric(latest["delta_wr_12m"], errors="coerce")

    # Volume anchors the score; 12-month share and win-rate movement rank trend-driving lines.
    latest["trend_score"] = (
        latest["share_of_games"] * 0.65
        + latest["delta_share_12m"].abs().fillna(0.0) * 8.0
        + latest["delta_wr_12m"].abs().fillna(0.0) * 20.0
    )

    top = latest.sort_values(["trend_score", "games"], ascending=[False, False]).head(limit)

    rows: list[dict] = []
    for _, r in top.iterrows():
        rows.append(
            {
                "month": latest_month,
                "uci": str(r.get("uci", "")),
                "san": str(r.get("san", "")),
                "games": int(r.get("games", 0)) if pd.notna(r.get("games")) else 0,
                "white_win_rate": float(r["white_win_rate"]) if pd.notna(r.get("white_win_rate")) else None,
                "share_of_games": float(r.get("share_of_games", 0.0)),
                "delta_share_12m": float(r["delta_share_12m"]) if pd.notna(r.get("delta_share_12m")) else None,
                "delta_wr_12m": float(r["delta_wr_12m"]) if pd.notna(r.get("delta_wr_12m")) else None,
            }
        )

    return rows


def _nav_html(current: str) -> str:
    pages = [
        ("index.html", "Overview"),
        ("openings.html", "Openings"),
        ("families.html", "Families"),
    ]
    links = ""
    for href, label in pages:
        active = ' class="nav-link active"' if href == current else ' class="nav-link"'
        links += f'<a href="{href}"{active}>{label}</a>\n    '

    return f"""<nav id="main-nav" class="site-nav">
  <div class="nav-inner">
    <span class="nav-wordmark">OpenCast</span>
    <div class="nav-links">
    {links}
    </div>
  </div>
</nav>"""


def _page_shell(title: str, nav_fragment: str, body: str, head_extras: str = "") -> str:
    _NAV_CSS = """
<style>
/* Site nav */
.site-nav {
  position: sticky; top: 0; z-index: 100;
  background: rgba(11,13,16,0.92);
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
  border-bottom: 1px solid rgba(255,255,255,0.07);
  height: 52px;
}
.nav-inner {
  max-width: 1200px; margin: 0 auto;
  width: 100%;
  box-sizing: border-box;
  padding: 0 2rem; height: 100%;
  display: flex; align-items: center;
  justify-content: center;
  gap: 1.75rem;
}
.nav-wordmark {
  font-family: 'Satoshi', 'Inter', sans-serif;
  font-weight: 700; font-size: 1.05rem;
  letter-spacing: -0.02em;
  color: var(--text-primary);
}
.nav-links { display: flex; gap: 1.5rem; align-items: center; }
.nav-link {
  font-size: 0.875rem; font-weight: 500;
  color: var(--text-secondary); text-decoration: none;
  transition: color 150ms;
}
.nav-link:hover, .nav-link.active { color: var(--text-primary); }
body { font-family: 'Satoshi', 'Inter', sans-serif; }
</style>"""
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{title} — OpenCast</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Instrument+Serif:ital@0;1&family=Inter:wght@300..600&display=swap" rel="stylesheet">
  <link href="https://api.fontshare.com/v2/css?f[]=satoshi@700,600,500,400&display=swap" rel="stylesheet">
  <link rel="stylesheet" href="assets/shared.css">
  {_NAV_CSS}
  {head_extras}
</head>
<body>
{nav_fragment}
<main><div class="page-content">
{body}
</div></main>
<script src="assets/nav.js"></script>
</body>
</html>
"""


def _serialize_openings_data(
    forecasts: pd.DataFrame,
    engine_df: pd.DataFrame,
    catalog: pd.DataFrame,
    findings_json: dict | None,
    narratives: dict | None = None,
    long_tail_df: pd.DataFrame | None = None,
    move_stats_df: pd.DataFrame | None = None,
    trend_signals: dict | None = None,
) -> dict[str, dict]:
    fallback_narrative = "No analysis available yet."
    # Prefer narratives.json for per-opening text (#18); fall back to findings.json
    if narratives and "per_opening" in narratives:
        per_opening = narratives["per_opening"]
    elif findings_json:
        per_opening = findings_json.get("per_opening", {})
    else:
        per_opening = {}

    ecos = catalog["eco"].astype(str).tolist() if (not catalog.empty and "eco" in catalog.columns) else []
    if not ecos and not forecasts.empty and "eco" in forecasts.columns:
        ecos = sorted(forecasts["eco"].dropna().astype(str).unique().tolist())

    serialized: dict[str, dict] = {}

    for eco in ecos:
        fc_eco = forecasts[forecasts["eco"] == eco].copy()
        if not fc_eco.empty:
            fc_eco = fc_eco.sort_values("month")

        cat_row = catalog[catalog["eco"] == eco] if not catalog.empty else pd.DataFrame()
        name = (
            str(cat_row["name"].iloc[0])
            if (not cat_row.empty and "name" in cat_row.columns)
            else (str(fc_eco["opening_name"].iloc[0]) if not fc_eco.empty else eco)
        )

        model_tier = None
        if not cat_row.empty and "model_tier" in cat_row.columns:
            try:
                model_tier = int(cat_row["model_tier"].iloc[0])
            except Exception:
                model_tier = None

        actuals_rows = fc_eco[fc_eco["is_forecast"] == False] if not fc_eco.empty else pd.DataFrame()
        forecast_rows = fc_eco[fc_eco["is_forecast"] == True] if not fc_eco.empty else pd.DataFrame()

        actuals = []
        for _, row in actuals_rows.iterrows():
            if pd.notna(row.get("actual")):
                actuals.append({"month": str(row["month"]), "win_rate": float(row["actual"])})

        forecast = []
        for _, row in forecast_rows.iterrows():
            forecast.append(
                {
                    "month": str(row["month"]),
                    "value": float(row["forecast"]) if pd.notna(row.get("forecast")) else None,
                    "lower": float(row["lower_ci"]) if pd.notna(row.get("lower_ci")) else None,
                    "upper": float(row["upper_ci"]) if pd.notna(row.get("upper_ci")) else None,
                }
            )

            forecast_quality = None
            model_name = None
            if not forecast_rows.empty and "forecast_quality" in forecast_rows.columns:
              qual = forecast_rows["forecast_quality"].dropna().astype(str)
              if not qual.empty:
                forecast_quality = str(qual.iloc[0]).lower()
            if not forecast_rows.empty and "model_name" in forecast_rows.columns:
              names = forecast_rows["model_name"].dropna().astype(str)
              if not names.empty:
                model_name = str(names.iloc[0])

        structural_breaks = []
        if not fc_eco.empty and "structural_break" in fc_eco.columns:
            structural_breaks = sorted(
                fc_eco[fc_eco["structural_break"] == True]["month"].astype(str).dropna().unique().tolist()
            )

        ed_row = engine_df[engine_df["eco"] == eco] if not engine_df.empty else pd.DataFrame()
        if ed_row.empty:
            engine_cp = None
            p_engine = None
            human_win_rate = None
            delta = None
            interpretation = None
        else:
            engine_cp = int(ed_row["engine_cp"].iloc[0]) if pd.notna(ed_row["engine_cp"].iloc[0]) else None
            p_engine = float(ed_row["p_engine"].iloc[0]) if pd.notna(ed_row["p_engine"].iloc[0]) else None
            human_win_rate = (
                float(ed_row["human_win_rate_2000"].iloc[0])
                if pd.notna(ed_row["human_win_rate_2000"].iloc[0])
                else None
            )
            delta = float(ed_row["delta"].iloc[0]) if pd.notna(ed_row["delta"].iloc[0]) else None
            interpretation = (
                str(ed_row["interpretation"].iloc[0]) if pd.notna(ed_row["interpretation"].iloc[0]) else None
            )

        narrative = per_opening.get(eco, fallback_narrative)

        # Long-tail stats for Tier-3 openings (#29)
        lt_stats: dict = {}
        if model_tier == 3 and long_tail_df is not None and not long_tail_df.empty:
            lt_row = long_tail_df[long_tail_df["eco"] == eco]
            if not lt_row.empty:
                r = lt_row.iloc[0]
                lt_stats = {
                    "last_month": str(r.get("last_month", "")),
                    "last_win_rate": float(r["last_win_rate"]) if pd.notna(r.get("last_win_rate")) else None,
                    "mean_win_rate": float(r["mean_win_rate"]) if pd.notna(r.get("mean_win_rate")) else None,
                    "std_win_rate": float(r["std_win_rate"]) if pd.notna(r.get("std_win_rate")) else None,
                    "ma3": float(r["ma3"]) if pd.notna(r.get("ma3")) else None,
                    "trend_direction": str(r.get("trend_direction", "flat")),
                    "months_available": int(r["months_available"]) if pd.notna(r.get("months_available")) else None,
                }

        # data_status: missing | sparse | ok (from openings_catalog.csv)
        data_status = "ok"
        if not cat_row.empty and "data_status" in cat_row.columns:
            data_status = str(cat_row["data_status"].iloc[0])

        sig = (trend_signals or {}).get(eco)
        lines_driving_trend = _top_lines_for_opening(move_stats_df, eco)
        # T3 openings have descriptive stats only — no model-selected forecast or quality
        if model_tier == 3:
            forecast_quality = None
            model_name = None
        serialized[eco] = {
            "name": name,
            "eco_group": eco[0] if eco else None,
            "model_tier": model_tier,
            "data_status": data_status,
            "actuals": actuals,
            "forecast": forecast,
            "structural_breaks": structural_breaks,
            "engine_cp": engine_cp,
            "p_engine": p_engine,
            "human_win_rate": human_win_rate,
            "delta": delta,
            "interpretation": interpretation,
            "narrative": str(narrative) if narrative is not None else fallback_narrative,
            "trend_direction": sig.direction if sig else "stable",
            "trend_slope_per_month": sig.slope_per_month if sig else 0.0,
            "trend_r_squared": sig.r_squared if sig else 0.0,
            "trend_confidence": sig.confidence if sig else "low",
            "trend_streak_months": sig.sustained_months if sig else 0,
            "forecast_quality": forecast_quality,
            "model_name": model_name,
            "lines_driving_trend": lines_driving_trend,
            **lt_stats,
        }

    return serialized


def render_opening_template() -> str:
    body = f"""
<h1 id="opening-title">Opening Detail</h1>
<p style="margin:-0.25rem 0 0.6rem 0; display:flex; gap:0.45rem; align-items:center; flex-wrap:wrap;">
  <span id="opening-tier-badge"></span>
  <span id="opening-model-badge"></span>
  <span id="opening-forecast-quality-badge"></span>
</p>
<p style="margin:0 0 1rem 0;">
  <a id="back-to-openings" href="openings.html" style="color:{TEXT_SECONDARY}; text-decoration:none; font-size:0.85rem;">&larr; All openings</a>
</p>
<div id="opening-narrative" class="engine-box" style="display:none;"><h3>Analysis</h3><p></p></div>
<div id="opening-chart"></div>
<div id="lines-box" class="engine-box" style="display:none;"></div>
<div id="engine-box" class="engine-box" style="display:none;"></div>

<script>
let openingsDataCache = null;
const ECO_COLORS = {json.dumps(ECO_COLORS)};
const PANEL_BG = "{PANEL_BG}";
const GRID_COLOR = "{GRID_COLOR}";
const TEXT_PRIMARY = "{TEXT_PRIMARY}";
const TEXT_SECONDARY = "{TEXT_SECONDARY}";
const BODY_FONT = {json.dumps(BODY_FONT)};
const DISPLAY_FONT = {json.dumps(DISPLAY_FONT)};
const FALLBACK_NARRATIVE = "No analysis available yet.";

function syncBackLink() {{
  const backLink = document.getElementById("back-to-openings");
  try {{
    const ref = document.referrer || "";
    if (ref.includes("openings.html#")) {{
      const refHash = ref.split("#")[1] || "";
      if (refHash) {{
        backLink.href = "openings.html#" + refHash;
        return;
      }}
    }}
  }} catch (_) {{}}
  const params = new URLSearchParams(window.location.search);
  const back = params.get("back");
  if (back) {{
    backLink.href = "openings.html#" + back;
  }}
}}

syncBackLink();

function hexToRgba(hexColor, alpha) {{
  const h = hexColor.replace("#", "");
  const r = parseInt(h.slice(0, 2), 16);
  const g = parseInt(h.slice(2, 4), 16);
  const b = parseInt(h.slice(4, 6), 16);
  return `rgba(${{r}}, ${{g}}, ${{b}}, ${{alpha}})`;
}}

function computeOlsTrend(actuals) {{
  if (!Array.isArray(actuals) || actuals.length < 3) return null;

  const points = actuals
    .map((d) => {{
      const t = Date.parse(`${{d.month}}-01T00:00:00Z`);
      const y = Number(d.win_rate);
      return Number.isFinite(t) && Number.isFinite(y) ? {{ x: t, y }} : null;
    }})
    .filter(Boolean);

  if (points.length < 3) return null;

  const n = points.length;
  const xMean = points.reduce((sum, p) => sum + p.x, 0) / n;
  const yMean = points.reduce((sum, p) => sum + p.y, 0) / n;

  let numerator = 0;
  let denominator = 0;
  for (const p of points) {{
    const dx = p.x - xMean;
    numerator += dx * (p.y - yMean);
    denominator += dx * dx;
  }}
  if (denominator === 0) return null;

  const slopePerMs = numerator / denominator;
  const intercept = yMean - slopePerMs * xMean;

  const trendY = actuals.map((d) => {{
    const t = Date.parse(`${{d.month}}-01T00:00:00Z`);
    return Number.isFinite(t) ? slopePerMs * t + intercept : null;
  }});

  const msPerMonth = 30.4375 * 24 * 60 * 60 * 1000;
  const slopePerMonth = slopePerMs * msPerMonth;
  const slopeThreshold = 0.0003;
  const direction = Math.abs(slopePerMonth) < slopeThreshold
    ? "stable"
    : (slopePerMonth > 0 ? "rising" : "falling");

  return {{ trendY, slopePerMonth, direction }};
}}

async function loadOpeningsData() {{
  if (openingsDataCache) {{
    return openingsDataCache;
  }}
  const response = await fetch("assets/openings_data.json", {{ cache: "no-store" }});
  if (!response.ok) {{
    throw new Error(`Failed to load openings_data.json (${{response.status}})`);
  }}
  openingsDataCache = await response.json();
  return openingsDataCache;
}}

function resolveEco(data) {{
  const ecos = Object.keys(data);
  if (!ecos.length) {{
    return null;
  }}
  const requested = new URLSearchParams(window.location.search).get("eco");
  if (requested && data[requested]) {{
    return requested;
  }}
  return ecos[0];
}}

function renderOpening(eco, opening) {{
  const name = opening.name || eco;
  document.getElementById("opening-title").textContent = `${{name}} (${{eco}})`;
  document.title = `${{eco}} — ${{name}} | OpenCast`;
  const tier = opening.model_tier;
  const tierBadge = document.getElementById("opening-tier-badge");
  const modelBadge = document.getElementById("opening-model-badge");
  const qualityBadge = document.getElementById("opening-forecast-quality-badge");
  const TIER_TOOLTIP = "T1: >=1000 avg monthly games + >=24 months -> model-selected forecast + engine evaluation\\nT2: 400-999 avg monthly games -> model-selected trend, no engine delta\\nT3: <400 avg monthly games -> descriptive stats only";
  if (tier) {{
    tierBadge.className = `tier-badge tier-badge-${{tier}}`;
    tierBadge.textContent = `T${{tier}}`;
    tierBadge.title = TIER_TOOLTIP;
  }} else {{
    tierBadge.textContent = "";
  }}

  const modelName = String(opening.model_name || "").trim();
  if (modelName && tier !== 3) {{
    modelBadge.className = "meta-badge";
    modelBadge.textContent = `Model: ${{modelName.replaceAll("_", "-")}}`;
  }} else {{
    modelBadge.className = "";
    modelBadge.textContent = "";
  }}

  const quality = String(opening.forecast_quality || "").toLowerCase();
  if (quality && tier !== 3) {{
    qualityBadge.className = `meta-badge quality-${{quality}}`;
    qualityBadge.textContent = `Forecast confidence: ${{quality}}`;
  }} else {{
    qualityBadge.className = "";
    qualityBadge.textContent = "";
  }}

  const narrativeBox = document.getElementById("opening-narrative");
  const narrative = opening.narrative || FALLBACK_NARRATIVE;
  if (!narrative || narrative === FALLBACK_NARRATIVE || !narrative.trim()) {{
    narrativeBox.style.display = "none";
  }} else {{
    narrativeBox.style.display = "";
    const narrativeEl = document.querySelector("#opening-narrative p");
    narrativeEl.textContent = narrative;
    narrativeEl.style.color = TEXT_PRIMARY;
  }}

  function renderLinesDrivingTrend(data) {{
    const box = document.getElementById("lines-box");
    const lines = Array.isArray(data.lines_driving_trend) ? data.lines_driving_trend : [];
    if (!lines.length) {{
      box.style.display = "none";
      box.innerHTML = "";
      return;
    }}

    const fmtPct = (v) => (v != null ? (v * 100).toFixed(2) + "%" : "—");
    const fmtPp = (v) => {{
      if (v == null) return "—";
      const pp = (v * 100).toFixed(2);
      return (v >= 0 ? "+" : "") + pp + " pp";
    }};

    const rows = lines.slice(0, 3).map((r) => `
      <tr>
        <td style="padding:0.45rem 0.6rem 0.45rem 0;"><strong style="color:${{TEXT_PRIMARY}};">${{r.san || "—"}}</strong><div style="font-size:0.74rem;color:${{TEXT_SECONDARY}};">${{r.uci || ""}}</div></td>
        <td style="padding:0.45rem 0.6rem;text-align:right;">${{fmtPct(r.share_of_games)}}</td>
        <td style="padding:0.45rem 0.6rem;text-align:right;">${{fmtPct(r.white_win_rate)}}</td>
        <td style="padding:0.45rem 0.6rem;text-align:right;color:${{(r.delta_wr_12m || 0) >= 0 ? "#7BE495" : "#F28DA6"}};">${{fmtPp(r.delta_wr_12m)}}</td>
      </tr>
    `).join("");

    const asOf = lines[0] && lines[0].month ? `As of ${{lines[0].month}}` : "Latest month";
    box.style.display = "block";
    box.innerHTML = `
      <h3>Lines Driving The Trend</h3>
      <p style="margin:0.25rem 0 0.8rem;color:${{TEXT_SECONDARY}};font-size:0.8rem;">Top move choices by volume and 12-month win-rate movement. ${{asOf}}.</p>
      <table style="width:100%;border-collapse:collapse;font-size:0.84rem;">
        <thead>
          <tr style="color:${{TEXT_SECONDARY}};font-size:0.72rem;text-transform:uppercase;letter-spacing:0.06em;">
            <th style="text-align:left;padding:0 0.6rem 0.35rem 0;">Move</th>
            <th style="text-align:right;padding:0 0.6rem 0.35rem;">Share</th>
            <th style="text-align:right;padding:0 0.6rem 0.35rem;">Win Rate</th>
            <th style="text-align:right;padding:0 0.6rem 0.35rem;">12m Δ WR</th>
          </tr>
        </thead>
        <tbody>${{rows}}</tbody>
      </table>`;
  }}

    // ── Missing data: no raw file was ever ingested ──────────────────────
    if (opening.data_status === "missing") {{
        document.getElementById("opening-chart").style.display = "none";
        document.getElementById("engine-box").style.display = "none";
      document.getElementById("lines-box").style.display = "none";
        narrativeBox.style.display = "none";
        const chartEl = document.getElementById("opening-chart");
        chartEl.style.display = "block";
        chartEl.innerHTML = `
            <div style="margin-top:2rem;padding:1.5rem 2rem;border:1px solid ${{GRID_COLOR}};border-radius:8px;">
                <p style="margin:0 0 0.75rem;font-size:1rem;font-weight:600;color:${{TEXT_PRIMARY}};">No game data available for this opening.</p>
                <p style="margin:0 0 1rem;font-size:0.875rem;color:${{TEXT_SECONDARY}};">This opening is classified as <strong style="color:${{TEXT_PRIMARY}};">Tier 3</strong> — it exists in the ECO catalog but doesn't meet the minimum volume threshold for analysis.</p>
                <table style="border-collapse:collapse;font-size:0.825rem;color:${{TEXT_SECONDARY}};">
                    <tr><td style="padding:0.3rem 1.2rem 0.3rem 0;white-space:nowrap;"><span class="tier-badge tier-badge-1">T1</span></td><td style="padding:0.3rem 0;">≥ 1 000 avg monthly games + ≥ 24 months of data — model-selected forecasting &amp; engine evaluation</td></tr>
                    <tr><td style="padding:0.3rem 1.2rem 0.3rem 0;"><span class="tier-badge tier-badge-2">T2</span></td><td style="padding:0.3rem 0;">400 – 999 avg monthly games — model-selected trend estimation, no engine delta</td></tr>
                    <tr><td style="padding:0.3rem 1.2rem 0.3rem 0;"><span class="tier-badge tier-badge-3">T3</span></td><td style="padding:0.3rem 0;">&lt; 400 avg monthly games — descriptive stats only, insufficient volume for modelling</td></tr>
                </table>
                <p style="margin:1rem 0 0;font-size:0.8rem;color:${{TEXT_SECONDARY}};opacity:0.7;">Data will appear here automatically once this opening meets the volume threshold.</p>
            </div>`;
        return;
    }}

    // ── Sparse data: fewer than 12 months, stats table with warning ────────
    if (opening.data_status === "sparse") {{
        document.getElementById("opening-chart").style.display = "none";
        document.getElementById("engine-box").style.display = "none";
      renderLinesDrivingTrend(opening);
        const fmtPct = (v) => (v != null ? (v * 100).toFixed(2) + "%" : "—");
        const fmt2   = (v) => (v != null ? (v * 100).toFixed(2) : "—");
        const trend = opening.trend_direction || "flat";
        const trendArrow = trend === "up" ? "↑" : trend === "down" ? "↓" : "→";
        const trendColor = trend === "up" ? "#7BE495" : trend === "down" ? "#F28DA6" : TEXT_SECONDARY;
        const chartEl = document.getElementById("opening-chart");
        chartEl.style.display = "block";
        chartEl.innerHTML = `
            <div style="margin-top:1rem;padding:0.75rem 1rem;border-left:3px solid #F28DA6;background:rgba(242,141,166,0.08);border-radius:4px;margin-bottom:1.5rem;">
                <p style="margin:0;font-size:0.85rem;color:#F28DA6;">Limited data (${{opening.months_available ?? 0}} months) — results may be unreliable.</p>
            </div>
            <div class="tier3-stats">
                <h2 style="font-size:1rem;font-weight:600;margin-bottom:1rem;color:${{TEXT_SECONDARY}};">Descriptive Statistics <span style="font-size:0.75rem;font-weight:400;">(sparse — insufficient data for modelling)</span></h2>
                <table style="border-collapse:collapse;width:100%;max-width:540px;"><tbody>
                    <tr><td style="padding:0.4rem 1rem 0.4rem 0;color:${{TEXT_SECONDARY}};">Last month</td><td style="padding:0.4rem 0;">${{opening.last_month || "—"}}</td></tr>
                    <tr><td style="padding:0.4rem 1rem 0.4rem 0;color:${{TEXT_SECONDARY}};">Last win rate</td><td style="padding:0.4rem 0;">${{fmtPct(opening.last_win_rate)}}</td></tr>
                    <tr><td style="padding:0.4rem 1rem 0.4rem 0;color:${{TEXT_SECONDARY}};">Mean win rate</td><td style="padding:0.4rem 0;">${{fmtPct(opening.mean_win_rate)}}</td></tr>
                    <tr><td style="padding:0.4rem 1rem 0.4rem 0;color:${{TEXT_SECONDARY}};">Std dev</td><td style="padding:0.4rem 0;">${{fmt2(opening.std_win_rate)}} pp</td></tr>
                    <tr><td style="padding:0.4rem 1rem 0.4rem 0;color:${{TEXT_SECONDARY}};">3-month MA</td><td style="padding:0.4rem 0;">${{fmtPct(opening.ma3)}}</td></tr>
                    <tr><td style="padding:0.4rem 1rem 0.4rem 0;color:${{TEXT_SECONDARY}};">Trend</td><td style="padding:0.4rem 0;color:${{trendColor}};">${{trendArrow}} ${{trend}}</td></tr>
                    <tr><td style="padding:0.4rem 1rem 0.4rem 0;color:${{TEXT_SECONDARY}};">Months of data</td><td style="padding:0.4rem 0;">${{opening.months_available ?? "—"}}</td></tr>
                </tbody></table>
            </div>`;
        return;
    }}

    // ── Tier 3: stats-only view ─────────────────────────────────────────────
    if (opening.model_tier === 3) {{
        document.getElementById("opening-chart").style.display = "none";
        document.getElementById("engine-box").style.display = "none";
      renderLinesDrivingTrend(opening);

        const trend = opening.trend_direction || "flat";
        const trendArrow = trend === "up" ? "↑" : trend === "down" ? "↓" : "→";
        const trendColor = trend === "up" ? "#7BE495" : trend === "down" ? "#F28DA6" : TEXT_SECONDARY;

        const fmtPct = (v) => (v != null ? (v * 100).toFixed(2) + "%" : "—");
        const fmt2   = (v) => (v != null ? (v * 100).toFixed(2) : "—");

        const statsHtml = `
            <div class="tier3-stats" style="margin-top:1.5rem;">
                <h2 style="font-size:1rem;font-weight:600;margin-bottom:1rem;color:${{TEXT_SECONDARY}};">
                    Descriptive Statistics <span style="font-size:0.75rem;font-weight:400;">(Tier 3 — insufficient data for modelling)</span>
                </h2>
                <table style="border-collapse:collapse;width:100%;max-width:540px;">
                    <tbody>
                        <tr><td style="padding:0.4rem 1rem 0.4rem 0;color:${{TEXT_SECONDARY}};">Last month</td>
                                <td style="padding:0.4rem 0;">${{opening.last_month || "—"}}</td></tr>
                        <tr><td style="padding:0.4rem 1rem 0.4rem 0;color:${{TEXT_SECONDARY}};">Last win rate</td>
                                <td style="padding:0.4rem 0;">${{fmtPct(opening.last_win_rate)}}</td></tr>
                        <tr><td style="padding:0.4rem 1rem 0.4rem 0;color:${{TEXT_SECONDARY}};">Mean win rate</td>
                                <td style="padding:0.4rem 0;">${{fmtPct(opening.mean_win_rate)}}</td></tr>
                        <tr><td style="padding:0.4rem 1rem 0.4rem 0;color:${{TEXT_SECONDARY}};">Std dev</td>
                                <td style="padding:0.4rem 0;">${{fmt2(opening.std_win_rate)}} pp</td></tr>
                        <tr><td style="padding:0.4rem 1rem 0.4rem 0;color:${{TEXT_SECONDARY}};">3-month MA</td>
                                <td style="padding:0.4rem 0;">${{fmtPct(opening.ma3)}}</td></tr>
                        <tr><td style="padding:0.4rem 1rem 0.4rem 0;color:${{TEXT_SECONDARY}};">Trend</td>
                                <td style="padding:0.4rem 0;color:${{trendColor}};">${{trendArrow}} ${{trend}}</td></tr>
                        <tr><td style="padding:0.4rem 1rem 0.4rem 0;color:${{TEXT_SECONDARY}};">Months of data</td>
                                <td style="padding:0.4rem 0;">${{opening.months_available ?? "—"}}</td></tr>
                    </tbody>
                </table>
            </div>`;

        const chartEl = document.getElementById("opening-chart");
        chartEl.style.display = "block";
        chartEl.innerHTML = statsHtml;
        return;
    }}

    const color = ECO_COLORS[(opening.eco_group || eco.charAt(0) || "").toUpperCase()] || "{ACCENT}";
    const actuals = opening.actuals || [];
    const forecasts = opening.forecast || [];
    const qualityLower = String(opening.forecast_quality || "").toLowerCase();
    const lowForecastQuality = qualityLower === "low";

  const traces = [
    {{
      x: actuals.map((d) => d.month),
      y: actuals.map((d) => d.win_rate),
      mode: "lines",
      name: "Actual",
      line: {{ color, width: 2 }},
      type: "scatter",
    }},
  ];

  if (forecasts.length) {{
    traces.push({{
      x: forecasts.map((d) => d.month),
      y: forecasts.map((d) => d.value),
      mode: "lines",
      name: "Forecast",
      line: {{ color, width: 1.5, dash: "dash" }},
      opacity: lowForecastQuality ? 0.46 : 0.95,
      type: "scatter",
    }});

    traces.push({{
      x: forecasts.map((d) => d.month).concat(forecasts.map((d) => d.month).slice().reverse()),
      y: forecasts.map((d) => d.upper).concat(forecasts.map((d) => d.lower).slice().reverse()),
      fill: "toself",
      fillcolor: hexToRgba(color, lowForecastQuality ? 0.07 : 0.12),
      line: {{ color: "rgba(0,0,0,0)" }},
      showlegend: false,
      name: "95% CI",
      type: "scatter",
    }});
  }}

  const olsTrend = computeOlsTrend(actuals);
  const trendConfidence = String(opening.trend_confidence || "low").toLowerCase();
  if (olsTrend) {{
    const trendDirection = String(opening.trend_direction || olsTrend.direction || "stable").toLowerCase();
    const trendColor = trendDirection === "rising" ? "#7BE495"
      : trendDirection === "falling" ? "#F28DA6" : TEXT_SECONDARY;
    traces.push({{
      x: actuals.map((d) => d.month),
      y: olsTrend.trendY,
      mode: "lines",
      name: `Trend (${{trendDirection}})` ,
      line: {{ color: trendColor, width: 1.5, dash: "longdash" }},
      opacity: trendConfidence === "high" ? 0.78 : trendConfidence === "medium" ? 0.55 : 0.30,
      type: "scatter",
    }});
  }}

  const layout = {{
    title: `${{eco}} — ${{name}}`,
    xaxis: {{ title: "Month", gridcolor: GRID_COLOR, zerolinecolor: GRID_COLOR, tickfont: {{ color: TEXT_SECONDARY }} }},
    yaxis: {{ title: "White Win Rate", gridcolor: GRID_COLOR, zerolinecolor: GRID_COLOR, tickfont: {{ color: TEXT_SECONDARY }} }},
    plot_bgcolor: PANEL_BG,
    paper_bgcolor: PANEL_BG,
    font: {{ family: BODY_FONT, color: TEXT_PRIMARY }},
    title_font: {{ family: DISPLAY_FONT, size: 18, color: TEXT_PRIMARY }},
    margin: {{ t: 60, r: 30, b: 60, l: 60 }},
  }};

  Plotly.newPlot("opening-chart", traces, layout, {{ responsive: true }});

  renderLinesDrivingTrend(opening);

  const engineBox = document.getElementById("engine-box");
  const hasEngine =
    opening.engine_cp !== null &&
    opening.p_engine !== null &&
    opening.human_win_rate !== null &&
    opening.delta !== null;

  if (!hasEngine) {{
    engineBox.style.display = "none";
    engineBox.innerHTML = "";
    return;
  }}

  const cp = Number(opening.engine_cp);
  const pEngine = Number(opening.p_engine);
  const human = Number(opening.human_win_rate);
  const delta = Number(opening.delta);
  const interpretation = opening.interpretation || "";

  engineBox.style.display = "block";
  engineBox.innerHTML = `
    <h3>Engine Evaluation</h3>
    <p>Stockfish depth-20: <strong>${{cp >= 0 ? "+" : ""}}${{cp}} cp</strong> → P(white wins) = ${{pEngine.toFixed(3)}}</p>
    <p>Human win rate (2000+): ${{human.toFixed(3)}}</p>
    <p>Delta: <strong>${{delta >= 0 ? "+" : ""}}${{delta.toFixed(3)}}</strong>${{interpretation ? ` — ${{interpretation}}` : ""}}</p>
  `;
}}

async function init() {{
  try {{
    const data = await loadOpeningsData();
    const eco = resolveEco(data);
    if (!eco) {{
      document.getElementById("opening-title").textContent = "No opening data available";
      return;
    }}
    renderOpening(eco, data[eco]);
  }} catch (error) {{
    document.getElementById("opening-title").textContent = "Failed to load opening data";
    const narrativeEl = document.querySelector("#opening-narrative p");
    narrativeEl.textContent = String(error);
    narrativeEl.style.color = TEXT_SECONDARY;
    document.getElementById("opening-narrative").style.display = "";
  }}
}}

init();
</script>
"""
    tier_css = f"""<style>
  .tier-badge {{display:inline-block;padding:0.15em 0.55em;border-radius:4px;font-size:0.75rem;font-weight:600;letter-spacing:0.04em;}}
  .tier-badge-1 {{background:rgba(74,158,255,0.18);color:#4a9eff;}}
  .tier-badge-2 {{background:rgba(169,117,255,0.18);color:#a975ff;}}
  .tier-badge-3 {{background:rgba(139,139,143,0.2);color:{TEXT_SECONDARY};}}
  .meta-badge {{display:inline-block;padding:0.15em 0.55em;border-radius:4px;font-size:0.75rem;font-weight:500;letter-spacing:0.02em;background:rgba(255,255,255,0.08);color:{TEXT_PRIMARY};}}
  .quality-high {{background:rgba(123,228,149,0.18);color:#7BE495;}}
  .quality-medium {{background:rgba(246,193,119,0.18);color:#F6C177;}}
  .quality-low {{background:rgba(242,141,166,0.18);color:#F28DA6;}}
</style>"""
    head_extras = tier_css + '\n<script src="https://cdn.plot.ly/plotly-2.35.2.min.js"></script>'
    return _page_shell("Opening Detail", _nav_html("openings.html"), body, head_extras=head_extras)


# -- Page renderers ------------------------------------------------------------
def render_overview(
    forecasts: pd.DataFrame,
    engine_df: pd.DataFrame,
    findings_json: dict | None,
) -> str:
    """Render data/output/dashboard/index.html — split hero + alternating analysis sections."""

    # ── Dynamic stats ─────────────────────────────────────────────────────
    n_openings = int(engine_df["eco"].nunique()) if not engine_df.empty else 0
    actuals_only = forecasts[forecasts["is_forecast"] == False] if not forecasts.empty else pd.DataFrame()
    fc_only = forecasts[forecasts["is_forecast"] == True] if not forecasts.empty else pd.DataFrame()
    n_months = int(actuals_only["month"].nunique()) if not actuals_only.empty else 0
    high_conf_openings = 0
    if not fc_only.empty and "forecast_quality" in fc_only.columns and "eco" in fc_only.columns:
      eco_quality = (
        fc_only.dropna(subset=["eco"])
        .groupby("eco", as_index=False)["forecast_quality"]
        .first()
      )
      high_conf_openings = int(
        eco_quality["forecast_quality"].astype(str).str.lower().eq("high").sum()
      )
    last_updated = (findings_json or {}).get("month", "—")

    # ── Findings insight text ─────────────────────────────────────────────
    panels = (findings_json or {}).get("panels", {})
    fc_insight = panels.get("forecast",     {}).get("insight", "")
    ed_insight = panels.get("engine_delta", {}).get("insight", "")
    hm_insight = panels.get("heatmap",      {}).get("insight", "")

    MAX_TITLE_CHARS = 60

    def _split_insight(text: str, fallback_title: str) -> tuple[str, str]:
      """Split 'First sentence. Rest.' and keep titles readable without truncation artifacts."""
      if not text or not str(text).strip():
        return fallback_title, ""

      clean = str(text).strip()
      parts = clean.split(". ", 1)
      title = parts[0].rstrip(".").strip() or fallback_title
      if len(title) > MAX_TITLE_CHARS:
        title = fallback_title

      body = parts[1].strip() if len(parts) > 1 else ""

      # If the first sentence was dropped (title fell back), the body may
      # begin with a dangling continuation word ("However,", "Additionally,",
      # etc.) that only made sense in context of the discarded sentence.
      # Strip it and capitalise the remainder.
      _CONTINUATIONS = ("however, ", "additionally, ", "furthermore, ",
                        "moreover, ", "conversely, ", "nevertheless, ",
                        "that said, ", "in addition, ", "as a result, ")
      body_lc = body.lower()
      for _cont in _CONTINUATIONS:
          if body_lc.startswith(_cont):
              body = body[len(_cont):].lstrip()
              body = body[0].upper() + body[1:] if body else body
              break

      return title, body

    fc_title, fc_body = _split_insight(fc_insight, "Win Rate Trends")
    ed_title, ed_body = _split_insight(ed_insight, "Engine vs Human Gap")
    hm_title, hm_body = _split_insight(hm_insight, "ECO Family Patterns")

    # ── Proof card data — computed from actual data ───────────────────────
    top_pos_eco = top_pos_name = top_neg_eco = top_neg_name = steep_eco = steep_name = "—"
    top_pos_delta_val = top_neg_delta_val = 0.0
    top_pos_human = top_pos_engine_exp = top_neg_human = top_neg_engine_exp = None
    steep_fc_delta: float | None = None

    if not engine_df.empty and "delta" in engine_df.columns:
        _df = engine_df.dropna(subset=["delta"]).copy()
        _pos = _df[_df["delta"] > 0].sort_values("delta", ascending=False)
        _neg = _df[_df["delta"] < 0].sort_values("delta", ascending=True)
        if not _pos.empty:
            _r = _pos.iloc[0]
            top_pos_eco = str(_r["eco"])
            top_pos_name = str(_r.get("opening_name", ""))
            top_pos_delta_val = float(_r["delta"])
            if "human_win_rate_2000" in _r.index:
                top_pos_human = float(_r["human_win_rate_2000"])
            if "p_engine" in _r.index:
                top_pos_engine_exp = float(_r["p_engine"])
        if not _neg.empty:
            _r = _neg.iloc[0]
            top_neg_eco = str(_r["eco"])
            top_neg_name = str(_r.get("opening_name", ""))
            top_neg_delta_val = float(_r["delta"])
            if "human_win_rate_2000" in _r.index:
                top_neg_human = float(_r["human_win_rate_2000"])
            if "p_engine" in _r.index:
                top_neg_engine_exp = float(_r["p_engine"])

    if not forecasts.empty:
        try:
            from .report import _full_series_ols
            _ols_results = _full_series_ols(forecasts)
            _best = next(
                (r for r in _ols_results if r[1] != "stable"),
                None,
            )
            if _best:
                steep_eco = _best[0]
                steep_fc_delta = _best[2]  # slope per month
                _n = forecasts[forecasts["eco"] == steep_eco]["opening_name"]
                steep_name = ""
                if not _n.empty:
                    _candidate = str(_n.iloc[0]).strip()
                    steep_name = _candidate if _candidate and _candidate != steep_eco else ""
                if not steep_name:
                    try:
                        _cat = pd.read_csv(os.path.join(os.path.dirname(__file__), "..", "data", "openings_catalog.csv"))
                        _cat_row = _cat[_cat["eco"] == steep_eco]
                        if not _cat_row.empty and "name" in _cat_row.columns:
                            steep_name = str(_cat_row["name"].iloc[0])
                    except Exception:
                        pass
        except Exception:
            pass

    top_pos_delta_str = f"+{top_pos_delta_val * 100:.2f} pp vs engine"
    top_neg_delta_str = f"{top_neg_delta_val * 100:.2f} pp vs engine"

    # Secondary stats for proof cards
    top_pos_extra = (
        f"Human win rate: {top_pos_human * 100:.1f}%"
        if top_pos_human is not None else ""
    )
    top_neg_extra = (
        f"Engine: {top_neg_engine_exp * 100:.1f}% &rarr; Human: {top_neg_human * 100:.1f}%"
        if top_neg_human is not None and top_neg_engine_exp is not None else ""
    )
    steep_extra = (
        f"OLS trend: {steep_fc_delta * 100:+.4f} pp/month"
        if steep_fc_delta is not None else ""
    )

    # ── Charts ────────────────────────────────────────────────────────────
    fig1 = _build_panel1_figure(forecasts, engine_df)
    fig1.update_layout(height=400, margin=dict(l=40, r=20, t=50, b=50))
    fig1_html = fig1.to_html(full_html=False, include_plotlyjs="cdn")

    fig2 = _build_panel2_figure(engine_df)
    fig2.update_layout(height=400, margin=dict(l=40, r=20, t=50, b=50))
    fig2_html = fig2.to_html(full_html=False, include_plotlyjs=False)

    fig3 = _build_panel3_figure(engine_df)
    fig3.update_layout(height=400, margin=dict(l=40, r=20, t=50, b=50))
    fig3_html = fig3.to_html(full_html=False, include_plotlyjs=False)

    # ── Overview-specific CSS (embedded in this page only) ────────────────
    _OV_CSS = """<style>
/* Variable aliases for overview components */
:root {
  --color-text:       var(--text-primary);
  --color-text-muted: var(--text-secondary);
  --color-text-faint: var(--text-faint);
  --color-surface:    var(--surface);
  --color-border:     var(--border);
  --color-primary:    #4DA3A6;
}

/* Satoshi for overview body */
body { font-family: 'Satoshi', 'Inter', sans-serif !important; }

/* Page-content override: let hero and sections self-manage their width */
.page-content { max-width: none !important; padding: 0 !important; }

.hero {
  display: grid;
  grid-template-columns: minmax(0, 1.03fr) minmax(0, 0.97fr);
  gap: 4rem;
  align-items: center;
  height: calc(100dvh - 52px);
  overflow: clip;
  width: 100%;
  padding-top: clamp(2rem, 5vw, 4rem);
  padding-bottom: clamp(2rem, 5vw, 4rem);
  padding-left:  max(1.5rem, calc((100vw - 1200px) / 2 + 1.5rem));
  padding-right: max(1.5rem, calc((100vw - 1200px) / 2 + 1.5rem));
  background-image: repeating-conic-gradient(
    rgba(255,255,255,0.015) 0% 25%,
    transparent 0% 50%
  );
  background-size: 48px 48px;
  background-position: 0 0;
  border-bottom: 1px solid rgba(255,255,255,0.07);
}
@media (max-width: 768px) {
  .hero { grid-template-columns: 1fr; gap: 3rem; height: auto; min-height: auto; overflow: visible; }
}

.hero-copy { }

.hero-eyebrow {
  font-size: 0.75rem; letter-spacing: 0.1em; text-transform: uppercase;
  color: var(--color-primary); font-weight: 600; margin: 0 0 1rem;
}
.hero-headline {
  font-family: 'Satoshi', 'Inter', sans-serif;
  font-size: clamp(2rem, 3.5vw, 2.75rem);
  font-weight: 700; line-height: 1.15; letter-spacing: -0.03em;
  color: var(--color-text); margin: 0 0 1.25rem;
}
.hero-word-theory {
  color: var(--color-primary);
  display: inline-block;
  animation: word-rise 0.6s cubic-bezier(0.16, 1, 0.3, 1) 0.3s both;
}
.hero-word-practical {
  color: #F28DA6;
  display: inline-block;
  animation: word-rise 0.6s cubic-bezier(0.16, 1, 0.3, 1) 0.55s both;
}
@keyframes word-rise {
  from { opacity: 0; transform: translateY(10px); }
  to   { opacity: 1; transform: translateY(0); }
}
.hero-body {
  font-size: 1rem; line-height: 1.7;
  color: var(--color-text-muted); max-width: 42ch; margin: 0 0 2rem;
}
.hero-stats { display: flex; flex-wrap: wrap; gap: 0.5rem; margin: 0 0 2rem; }
.stat-pill {
  font-size: 0.75rem; padding: 0.3rem 0.75rem;
  border: 1px solid rgba(255,255,255,0.1);
  border-radius: 9999px; color: var(--color-text-muted);
  font-variant-numeric: tabular-nums;
}
.hero-actions { display: flex; gap: 1rem; flex-wrap: wrap; }
.btn-primary {
  padding: 0.6rem 1.4rem; background: var(--color-primary);
  color: #0B0D10; border-radius: 6px; font-size: 0.875rem;
  font-weight: 600; text-decoration: none; display: inline-block;
  transition: opacity 150ms;
}
.btn-primary:hover { opacity: 0.85; }
.btn-secondary {
  padding: 0.6rem 1.4rem; border: 1px solid rgba(255,255,255,0.15);
  color: var(--color-text-muted); border-radius: 6px;
  font-size: 0.875rem; text-decoration: none; display: inline-block;
  transition: border-color 150ms, color 150ms;
}
.btn-secondary:hover { border-color: rgba(255,255,255,0.3); color: var(--color-text); }

/* Hero right: proof cards */
.hero-visual { display: flex; flex-direction: column; gap: 1rem; width: 100%; align-items: stretch; align-self: center; justify-content: center; }
.proof-card {
  background: var(--color-surface);
  border: 1px solid rgba(255,255,255,0.08);
  border-radius: 12px; padding: 1.25rem 1.5rem;
  width: 100%;
  box-sizing: border-box;
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  transition: transform 200ms;
}
.proof-card:hover { transform: translateY(-2px); }
@media (prefers-reduced-motion: reduce) { .proof-card { transition: none; } }
.proof-label {
  font-size: 0.7rem; text-transform: uppercase; letter-spacing: 0.08em;
  color: var(--color-text-faint); margin: 0 0 0.4rem;
}
.proof-value { font-size: 1.25rem; font-weight: 700; color: var(--color-text); }
.proof-detail { font-size: 0.8rem; color: var(--color-text-muted); margin: 0.2rem 0 0; white-space: normal; word-break: break-word; line-height: 1.3; }
.proof-extra  { font-size: 0.75rem; color: var(--color-text-faint); margin: 0.35rem 0 0; }
.proof-delta { font-size: 0.875rem; font-weight: 600; margin: 0.5rem 0 0; }
.proof-delta.positive { color: #4DA3A6; }
.proof-delta.negative { color: #d163a7; }
.proof-delta.neutral  { color: var(--color-text-muted); }
.proof-link {
  color: inherit;
  text-decoration: none;
  display: inline-block;
}
.proof-link:hover .proof-value { text-decoration: underline; text-underline-offset: 3px; }
.proof-card-eco-link {
  color: var(--color-text);
  text-decoration: underline;
  text-underline-offset: 3px;
  text-decoration-color: rgba(255,255,255,0.25);
  display: inline-block;
}
.proof-card-eco-link:hover { text-decoration-color: var(--color-primary); color: var(--color-primary); }

/* Analysis sections */
.analysis-section {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 3rem;
  max-width: 1200px;
  margin: 0 auto 5rem;
  padding: 4rem 2rem 0;
  align-items: start;
}
.analysis-section.reverse { direction: rtl; }
.analysis-section.reverse > * { direction: ltr; }
@media (max-width: 768px) {
  .analysis-section, .analysis-section.reverse {
    grid-template-columns: 1fr; direction: ltr; padding: 2.5rem 1.5rem 0;
  }
}

.section-copy { padding-top: 1rem; }
.section-eyebrow {
  font-size: 0.7rem; text-transform: uppercase; letter-spacing: 0.1em;
  color: var(--color-primary); font-weight: 600; margin: 0 0 0.75rem;
}
.section-title {
  font-size: 1.4rem; font-weight: 700; letter-spacing: -0.02em;
  color: var(--color-text); margin: 0 0 0.75rem; line-height: 1.3;
}
.section-body {
  font-size: 0.9375rem; line-height: 1.7;
  color: var(--color-text-muted); max-width: 44ch; margin: 0;
}
.section-chart { min-width: 0; }

/* Browse link */
.browse-link {
  text-align: right; color: var(--color-text-faint);
  font-size: 0.8rem; max-width: 1200px; margin: 0 auto;
  padding: 1.5rem 2rem 4rem;
}
.browse-link a { color: var(--color-primary); text-decoration: none; }
.browse-link a:hover { text-decoration: underline; }
</style>
<script>
(function() {
  function animateCount(el, target, duration, suffix) {
    var start = performance.now();
    (function tick(now) {
      var progress = Math.min((now - start) / duration, 1);
      var eased = 1 - Math.pow(1 - progress, 3);
      el.textContent = Math.floor(eased * target) + suffix;
      if (progress < 1) requestAnimationFrame(tick);
    })(start);
  }
  document.addEventListener('DOMContentLoaded', function() {
    document.querySelectorAll('.stat-pill[data-count]').forEach(function(el) {
      var target = parseInt(el.getAttribute('data-count'), 10);
      var suffix = el.getAttribute('data-suffix') || '';
      animateCount(el, target, 1200, suffix);
    });
  });
})();
</script>"""

    def _proof_card(label: str, eco: str, name: str, delta_class: str, delta_text: str, extra: str = "") -> str:
        if eco != "—":
            value_html = f'<a class="proof-card-eco-link" href="opening.html?eco={eco}"><p class="proof-value">{eco}</p></a>'
            detail_html = f'<a class="proof-link" href="opening.html?eco={eco}"><p class="proof-detail">{name}</p></a>'
        else:
            value_html = f'<p class="proof-value">{eco}</p>'
            detail_html = f'<p class="proof-detail">{name}</p>'
        extra_html = f'<p class="proof-extra">{extra}</p>' if extra else ""
        return (
            '<div class="proof-card">'
            f'<p class="proof-label">{label}</p>'
            f'{value_html}'
            f'{detail_html}'
            f'{extra_html}'
            f'<p class="proof-delta {delta_class}">{delta_text}</p>'
            '</div>'
        )

    # ── Hero HTML ─────────────────────────────────────────────────────────
    hero_html = (
      '<section class="hero">'
        '<div class="hero-copy">'
        '<p class="hero-eyebrow">Monthly chess opening intelligence</p>'
        '<h1 class="hero-headline">Track where opening '
        '<span class="hero-word-theory">theory</span>'
        ' and <span class="hero-word-practical">practical play</span> diverge.</h1>'
        '<p class="hero-body">OpenCast analyzes monthly Lichess opening data, forecasts '
        'win-rate movement, and highlights where human results outperform or lag behind '
        'engine expectation.</p>'
        '<div class="hero-stats">'
        f'<div class="stat-pill" data-count="{n_openings}" data-suffix=" openings tracked">'
        f'{n_openings} openings tracked</div>'
        f'<div class="stat-pill" data-count="{n_months}" data-suffix=" months of data">'
        f'{n_months} months of data</div>'
        f'<div class="stat-pill" data-count="{high_conf_openings}" data-suffix=" high-confidence forecasts">'
        f'{high_conf_openings} high-confidence forecasts</div>'
        f'<div class="stat-pill">Last updated: {last_updated}</div>'
        '</div>'
        '<div class="hero-actions">'
        '<a href="openings.html" class="btn-primary">Explore openings</a>'
        '<a href="families.html" class="btn-secondary">ECO families</a>'
        '</div>'
        '</div>'
        '<div class="hero-visual">'
        + _proof_card("Top outperformer", top_pos_eco, top_pos_name, "positive", top_pos_delta_str, top_pos_extra)
        + _proof_card("Largest engine gap", top_neg_eco, top_neg_name, "negative", top_neg_delta_str, top_neg_extra)
        + _proof_card("Steepest rising trend", steep_eco, steep_name, "neutral", "\u2191 Forecast rising", steep_extra)
        + '</div>'
        '</section>'
    )

    def _section(eyebrow: str, title: str, body_text: str, chart_html: str, reverse: bool = False) -> str:
        cls = "analysis-section reverse" if reverse else "analysis-section"
        return (
            f'<section class="{cls}">'
            '<div class="section-copy">'
            f'<p class="section-eyebrow">{eyebrow}</p>'
            f'<h2 class="section-title">{title or eyebrow}</h2>'
            f'<p class="section-body">{body_text}</p>'
            '</div>'
            f'<div class="section-chart">{chart_html}</div>'
            '</section>'
        )

    fc_body_text = fc_body or fc_insight or "Recent forecast signal is limited; monitor upcoming months for clearer direction."
    ed_body_text = ed_body or ed_insight or "Engine and practical outcomes are compared to identify where play diverges from theory."
    hm_body_text = hm_body or hm_insight or "Family-level win-rate aggregates highlight where practical performance clusters."

    body = (
        hero_html
      + _section("Win Rate Forecasts", fc_title, fc_body_text, fig1_html)
      + _section("Engine Delta", ed_title, ed_body_text, fig2_html, reverse=True)
      + _section("ECO Family Win Rates", hm_title, hm_body_text, fig3_html)
        + '<p class="browse-link"><a href="openings.html">\u2192 Browse all openings</a></p>'
    )

    return _page_shell("Overview", _nav_html("index.html"), body, head_extras=_OV_CSS)


def render_openings_table(
    forecasts: pd.DataFrame,
    engine_df: pd.DataFrame,
    catalog: pd.DataFrame,
) -> str:
    """Render data/output/dashboard/openings.html - client-side searchable/filterable/sortable table (#30)."""
    eco_colors_js = json.dumps(ECO_COLORS)

    group_options = "".join(
      f'<option value="{g}">{g}</option>'
        for g in sorted(ECO_COLORS)
    )

    table_html = f"""
<h1 class="page-title">All Openings</h1>

<div id="table-controls" style="display:flex;flex-wrap:wrap;gap:0.75rem;align-items:center;margin-bottom:1.25rem;">
  <input id="search-box" type="search" placeholder="Search ECO or name..."
    aria-label="Search openings"
    style="flex:1;min-width:200px;max-width:360px;padding:0.4rem 0.75rem;
           background:var(--surface-raised);border:1px solid rgba(255,255,255,0.12);
           border-radius:6px;color:var(--text-primary);font-size:0.9rem;outline:none;
           font-family:'Satoshi','Inter',sans-serif;" />

  <select id="group-select"
    style="padding:0.35rem 0.6rem;background:var(--surface-raised);
           border:1px solid rgba(255,255,255,0.12);border-radius:6px;
           color:var(--text-primary);font-size:0.85rem;cursor:pointer;
           font-family:'Satoshi','Inter',sans-serif;">
    <option value="">All classes</option>
    {group_options}
  </select>

  <select id="tier-select"
    style="padding:0.35rem 0.6rem;background:var(--surface-raised);
           border:1px solid rgba(255,255,255,0.12);border-radius:6px;
           color:var(--text-primary);font-size:0.85rem;cursor:pointer;
           font-family:'Satoshi','Inter',sans-serif;">
    <option value="">All tiers</option>
    <option value="1">Tier 1</option>
    <option value="2">Tier 2</option>
    <option value="3">Tier 3</option>
  </select>

  <select id="quality-select"
    style="padding:0.35rem 0.6rem;background:var(--surface-raised);
           border:1px solid rgba(255,255,255,0.12);border-radius:6px;
           color:var(--text-primary);font-size:0.85rem;cursor:pointer;
           font-family:'Satoshi','Inter',sans-serif;">
    <option value="">All confidence</option>
    <option value="high">High</option>
    <option value="medium">Medium</option>
    <option value="low">Low</option>
  </select>

  <span id="row-count" style="color:{TEXT_SECONDARY};font-size:0.85rem;margin-left:auto;white-space:nowrap;"></span>
</div>

<div style="margin:0 0 1.25rem 0;padding:0.8rem 1rem;border:1px solid rgba(255,255,255,0.10);border-radius:8px;background:rgba(255,255,255,0.02);font-family:'Satoshi','Inter',sans-serif;">
  <div style="font-size:0.82rem;color:{TEXT_SECONDARY};line-height:1.6;">
    <strong style="color:{TEXT_PRIMARY};">Tier 1</strong>: at least 1,000 average monthly games and at least 24 months of data (full forecast + engine comparison).<br>
    <strong style="color:{TEXT_PRIMARY};">Tier 2</strong>: 400–999 average monthly games (trend forecast only).<br>
    <strong style="color:{TEXT_PRIMARY};">Tier 3</strong>: under 400 average monthly games (descriptive stats only).
  </div>
</div>

<div style="overflow-x:auto;">
<table id="openings-table" class="data-table" style="width:100%;border-collapse:collapse;">
  <thead>
    <tr>
      <th class="sortable" data-col="eco"      style="cursor:pointer;white-space:nowrap;">ECO <span class="sort-icon"></span></th>
      <th class="sortable" data-col="name"     style="cursor:pointer;white-space:nowrap;">Name <span class="sort-icon"></span></th>
      <th class="sortable" data-col="tier"     style="cursor:pointer;white-space:nowrap;">Tier <span class="sort-icon"></span></th>
      <th class="sortable" data-col="win_rate" style="cursor:pointer;white-space:nowrap;">Win Rate (last) <span class="sort-icon"></span></th>
      <th class="sortable" data-col="has_fc"   style="cursor:pointer;white-space:nowrap;">Forecast <span class="sort-icon"></span></th>
      <th class="sortable" data-col="quality"  style="cursor:pointer;white-space:nowrap;">Confidence <span class="sort-icon"></span></th>
      <th class="sortable" data-col="delta"    style="cursor:pointer;white-space:nowrap;">Engine Delta <span class="sort-icon"></span></th>
      <th>Detail</th>
    </tr>
  </thead>
  <tbody id="openings-tbody"></tbody>
</table>
</div>
<p id="empty-state" style="display:none;color:{TEXT_SECONDARY};text-align:center;padding:2rem;">
  No openings match the current filters.
</p>

<style>
#openings-table tbody tr:hover {{ background: rgba(255,255,255,0.04); cursor:pointer; }}
#openings-table th {{ user-select:none; }}
.sort-icon {{ font-size:0.75rem; opacity:0.5; }}
.tier-badge {{ display:inline-block;padding:0.15em 0.55em;border-radius:4px;font-size:0.75rem;font-weight:600;letter-spacing:0.04em; }}
.tier-badge-1 {{ background:rgba(74,158,255,0.18);color:#4a9eff; }}
.tier-badge-2 {{ background:rgba(169,117,255,0.18);color:#a975ff; }}
.tier-badge-3 {{ background:rgba(139,139,143,0.2);color:{TEXT_SECONDARY}; }}
.quality-badge {{ display:inline-block;padding:0.15em 0.55em;border-radius:4px;font-size:0.72rem;font-weight:600;letter-spacing:0.03em;text-transform:capitalize; }}
.quality-badge-high {{ background:rgba(123,228,149,0.18);color:#7BE495; }}
.quality-badge-medium {{ background:rgba(246,193,119,0.18);color:#F6C177; }}
.quality-badge-low {{ background:rgba(242,141,166,0.18);color:#F28DA6; }}
</style>

<script>
(async () => {{
  const ECO_COLORS = {eco_colors_js};
  const TEXT_SECONDARY = "{TEXT_SECONDARY}";
  const TEXT_PRIMARY   = "{TEXT_PRIMARY}";
  const ACCENT         = "{ACCENT}";

  let openingsData = {{}};
  try {{
    const resp = await fetch("assets/openings_data.json", {{ cache: "no-store" }});
    if (!resp.ok) throw new Error("HTTP " + resp.status);
    openingsData = await resp.json();
  }} catch (e) {{
    const es = document.getElementById("empty-state");
    es.style.display = "block";
    es.textContent = "Failed to load openings data.";
    return;
  }}

  const allRows = Object.entries(openingsData).map(([eco, d]) => {{
    const actuals = d.actuals || [];
    const lastActual = actuals.length ? actuals[actuals.length - 1].win_rate : null;
    return {{
      eco,
      name: d.name || eco,
      group: (eco[0] || "").toUpperCase(),
      tier: d.model_tier != null ? d.model_tier : 99,
      win_rate: lastActual,
      has_fc: (d.forecast || []).length > 0,
      quality: String(d.forecast_quality || "").toLowerCase(),
      delta: d.delta != null ? d.delta : null,
    }};
  }});
  const total = allRows.length;

  const state = {{
    q: "",
    group: "",
    tier: "",
    quality: "",
    sortCol: "eco",
    asc: true,
  }};

  function readHash() {{
    const h = window.location.hash.slice(1);
    if (!h) return;
    try {{
      const p = new URLSearchParams(h);
      if (p.has("q"))       state.q = p.get("q");
      if (p.has("group"))   state.group = p.get("group");
      if (p.has("tier"))    state.tier = p.get("tier");
      if (p.has("quality")) state.quality = p.get("quality");
      if (p.has("sort"))    state.sortCol = p.get("sort");
      if (p.has("asc"))     state.asc = p.get("asc") !== "0";
    }} catch (_) {{}}
  }}

  function writeHash() {{
    const p = new URLSearchParams();
    if (state.q) p.set("q", state.q);
    if (state.group) p.set("group", state.group);
    if (state.tier) p.set("tier", state.tier);
    if (state.quality) p.set("quality", state.quality);
    p.set("sort", state.sortCol);
    p.set("asc", state.asc ? "1" : "0");
    history.replaceState(null, "", "#" + p.toString());
  }}

  readHash();

  const searchBox = document.getElementById("search-box");
  const groupSelect = document.getElementById("group-select");
  const tierSelect = document.getElementById("tier-select");
  const qualitySelect = document.getElementById("quality-select");
  const tbody = document.getElementById("openings-tbody");
  const rowCount = document.getElementById("row-count");
  const emptyState = document.getElementById("empty-state");
  const sortHeaders = document.querySelectorAll(".sortable");

  searchBox.value = state.q;
  groupSelect.value = state.group;
  tierSelect.value = state.tier;
  qualitySelect.value = state.quality;

  function applyFilters() {{
    const q = state.q.toLowerCase();
    const tier = state.tier;
    const quality = state.quality;
    let visible = allRows.filter(r => {{
      if (state.group && r.group !== state.group) return false;
      if (tier && String(r.tier) !== tier) return false;
      if (quality && String(r.quality || "") !== quality) return false;
      if (q && !r.eco.toLowerCase().includes(q) && !r.name.toLowerCase().includes(q)) return false;
      return true;
    }});
    visible.sort((a, b) => {{
      let av = a[state.sortCol], bv = b[state.sortCol];
      if (av == null && bv == null) return 0;
      if (av == null) return 1;
      if (bv == null) return -1;
      if (typeof av === "string") av = av.toLowerCase();
      if (typeof bv === "string") bv = bv.toLowerCase();
      if (av < bv) return state.asc ? -1 : 1;
      if (av > bv) return state.asc ? 1 : -1;
      return 0;
    }});
    writeHash();
    renderRows(visible);
    rowCount.textContent = "Showing " + visible.length + " of " + total;
    emptyState.style.display = visible.length === 0 ? "block" : "none";
    updateSortIcons();
  }}

  function fmtPct(v)   {{ return v != null ? (v * 100).toFixed(2) + "%" : "—"; }}
  function fmtDelta(v) {{
    if (v == null) return "—";
    return (v >= 0 ? "+" : "") + (v * 100).toFixed(2) + " pp";
  }}
  function deltaColor(v) {{
    if (v == null) return TEXT_SECONDARY;
    return v > 0.005 ? "#7BE495" : v < -0.005 ? "#F28DA6" : TEXT_SECONDARY;
  }}
  const TIER_TOOLTIP = "T1: >=1000 avg monthly games + >=24 months -> model-selected forecast + engine evaluation\\nT2: 400-999 avg monthly games -> model-selected trend, no engine delta\\nT3: <400 avg monthly games -> descriptive stats only";
  function tierBadge(t) {{
    return '<span class="tier-badge tier-badge-' + t + '" title="' + TIER_TOOLTIP + '">T' + t + '</span>';
  }}
  function qualityBadge(q, tier) {{
    if (!q || tier === 3) return '<span style="color:' + TEXT_SECONDARY + '">—</span>';
    const cls = 'quality-badge quality-badge-' + q;
    return '<span class="' + cls + '">' + q + '</span>';
  }}

  function renderRows(rows) {{
    const html = rows.map(r => {{
      const color = ECO_COLORS[r.group] || TEXT_PRIMARY;
      const backState = window.location.hash.slice(1);
      const href  = "opening.html?eco=" + encodeURIComponent(r.eco) + (backState ? "&back=" + backState : "");
      return '<tr tabindex="0" role="link"' +
        ' onclick="location.href=\\'' + href + '\\'"' +
          ' onkeydown="if(event.key===\\'Enter\\'||event.key===\\' \\'){{event.preventDefault();location.href=\\'' + href + '\\'}}">' +
        '<td style="font-weight:600;color:' + color + '">' + r.eco + '</td>' +
        '<td>' + r.name + '</td>' +
        '<td style="text-align:center;">' + tierBadge(r.tier) + '</td>' +
        '<td style="text-align:right;">' + fmtPct(r.win_rate) + '</td>' +
        '<td style="text-align:center;">' + (r.has_fc ? "Yes" : '<span style="color:' + TEXT_SECONDARY + '">No</span>') + '</td>' +
        '<td style="text-align:center;">' + qualityBadge(r.quality, r.tier) + '</td>' +
        '<td style="text-align:right;color:' + deltaColor(r.delta) + '">' + fmtDelta(r.delta) + '</td>' +
        '<td style="text-align:center;"><a href="' + href + '" style="color:{ACCENT};text-decoration:none;" onclick="event.stopPropagation()">Details</a></td>' +
        '</tr>';
    }}).join("");
    tbody.innerHTML = html || "";
  }}

  function updateSortIcons() {{
    sortHeaders.forEach(th => {{
      const icon = th.querySelector(".sort-icon");
      if (th.getAttribute("data-col") === state.sortCol) {{
        icon.textContent = state.asc ? " ^" : " v";
        icon.style.opacity = "1";
      }} else {{
        icon.textContent = " ^v";
        icon.style.opacity = "0.3";
      }}
    }});
  }}

  let debounceTimer;
  searchBox.addEventListener("input", () => {{
    clearTimeout(debounceTimer);
    debounceTimer = setTimeout(() => {{ state.q = searchBox.value.trim(); applyFilters(); }}, 200);
  }});
  groupSelect.addEventListener("change", () => {{ state.group = groupSelect.value; applyFilters(); }});
  tierSelect.addEventListener("change", () => {{ state.tier = tierSelect.value; applyFilters(); }});
  qualitySelect.addEventListener("change", () => {{ state.quality = qualitySelect.value; applyFilters(); }});
  sortHeaders.forEach(th => {{
    th.addEventListener("click", () => {{
      const col = th.getAttribute("data-col");
      if (state.sortCol === col) {{ state.asc = !state.asc; }}
      else {{ state.sortCol = col; state.asc = true; }}
      applyFilters();
    }});
  }});

  applyFilters();
}})();
</script>
"""
    return _page_shell("All Openings", _nav_html("openings.html"), table_html)


def render_families(forecasts: pd.DataFrame) -> str:
    """Render data/output/dashboard/families.html with dashboard-consistent layout."""
    actuals = forecasts[forecasts["is_forecast"] == False].copy()
    if not actuals.empty:
        actuals["eco_group"] = actuals["eco"].astype(str).str[0]
    else:
        actuals = pd.DataFrame(columns=["eco_group", "eco", "actual"])

    summary = []
    for group in sorted(ECO_COLORS):
        sub = actuals[actuals["eco_group"] == group]
        summary.append(
            {
                "group": group,
                "n_ecos": int(sub["eco"].nunique()) if not sub.empty else 0,
                "avg_wr": float(sub["actual"].mean()) if not sub.empty else None,
            }
        )

    total_ecos = sum(s["n_ecos"] for s in summary)
    weighted_mean = (
        sum((s["avg_wr"] or 0.0) * s["n_ecos"] for s in summary) / total_ecos
        if total_ecos > 0
        else None
    )

    rows_html = ""
    for s in summary:
        color = ECO_COLORS.get(s["group"], TEXT_PRIMARY)
        wr = f"{s['avg_wr']:.3f}" if s["avg_wr"] is not None else "—"
        rows_html += (
            "<tr>"
            f'<td><span class="family-chip" style="--chip-color:{color}">{s["group"]}</span></td>'
            f"<td>{s['n_ecos']}</td>"
            f"<td>{wr}</td>"
            "</tr>"
        )

    _FAM_CSS = """<style>
.families-shell { max-width: 1200px; margin: 0 auto; padding: 3rem 2rem 4rem; }
.families-hero { display: grid; grid-template-columns: 1.2fr 1fr; gap: 1.25rem; margin-bottom: 2rem; }
.engine-box {
  background: var(--surface-raised);
  border: 1px solid rgba(255,255,255,0.10);
  border-radius: 12px;
  padding: 1rem 1.1rem;
}
.families-title { margin: 0 0 0.45rem; font-size: 1.8rem; letter-spacing: -0.02em; }
.families-subtitle { margin: 0; color: var(--text-secondary); line-height: 1.6; }
.metric-label { margin: 0 0 0.25rem; font-size: 0.78rem; color: var(--text-faint); text-transform: uppercase; letter-spacing: 0.08em; }
.metric-value { margin: 0; font-size: 1.35rem; font-weight: 700; color: var(--text-primary); }
.analysis-section { display: grid; grid-template-columns: 1fr; gap: 1rem; }
.family-chip {
  display: inline-block;
  min-width: 1.75rem;
  text-align: center;
  padding: 0.15rem 0.45rem;
  border-radius: 6px;
  background: color-mix(in srgb, var(--chip-color) 20%, transparent);
  color: var(--chip-color);
  font-weight: 700;
}
@media (max-width: 900px) {
  .families-shell { padding: 2rem 1.25rem 3rem; }
  .families-hero { grid-template-columns: 1fr; }
}
</style>"""

    mean_text = f"{weighted_mean:.3f}" if weighted_mean is not None else "—"
    body = f"""
<section class="families-shell">
  <section class="families-hero">
    <div class="engine-box">
      <h1 class="families-title">ECO Families</h1>
      <p class="families-subtitle">Family-level performance summary using historical observed win rates across tracked openings.</p>
    </div>
    <div class="engine-box">
      <p class="metric-label">Tracked Openings</p>
      <p class="metric-value">{total_ecos}</p>
      <p class="metric-label" style="margin-top:0.9rem;">Weighted Avg Win Rate</p>
      <p class="metric-value">{mean_text}</p>
    </div>
  </section>

  <section class="analysis-section">
    <div class="engine-box">
      <table class="data-table" style="margin:0;">
        <thead>
          <tr><th>Family</th><th>Openings tracked</th><th>Avg win rate</th></tr>
        </thead>
        <tbody>{rows_html}</tbody>
      </table>
    </div>
  </section>
</section>
"""
    return _page_shell("Families", _nav_html("families.html"), body, head_extras=_FAM_CSS)


# -- Orchestrator --------------------------------------------------------------
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

    for asset_name in ("shared.css", "nav.js"):
        src = Path(__file__).parent / "assets" / asset_name
        dst = Path(ASSETS_DIR) / asset_name
        if src.exists():
            import shutil

            shutil.copy2(src, dst)

    overview_html = render_overview(forecasts, engine_df, findings)
    overview_path = os.path.join(OUTPUT_DIR, "index.html")
    Path(overview_path).write_text(overview_html, encoding="utf-8")
    print(f"Overview written -> {overview_path}")

    if not catalog.empty:
        openings_html = render_openings_table(forecasts, engine_df, catalog)
        openings_path = os.path.join(OUTPUT_DIR, "openings.html")
        Path(openings_path).write_text(openings_html, encoding="utf-8")
        print(f"Openings table written -> {openings_path}")

    from .report import _forecast_directions
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
        import shutil

        shutil.rmtree(stale_dir)

    families_html = render_families(forecasts)
    families_path = os.path.join(OUTPUT_DIR, "families.html")
    Path(families_path).write_text(families_html, encoding="utf-8")
    print(f"Families page written -> {families_path}")

    print(f"\nDashboard written -> {OUTPUT_DIR}/ ({len(openings_data)} ECOs)")


if __name__ == "__main__":
    run_visualizer()
