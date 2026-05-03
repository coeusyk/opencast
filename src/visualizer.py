import json
import os
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go

_HERE = os.path.dirname(__file__)
FORECASTS_CSV = os.path.join(_HERE, "..", "data", "output", "forecasts.csv")
ENGINE_CSV = os.path.join(_HERE, "..", "data", "output", "engine_delta.csv")
CATALOG_CSV = os.path.join(_HERE, "..", "data", "openings_catalog.csv")
FINDINGS_JSON = os.path.join(_HERE, "..", "findings", "findings.json")
OUTPUT_DIR = os.path.join(_HERE, "..", "data", "output", "dashboard")
ASSETS_DIR = os.path.join(OUTPUT_DIR, "assets")

# -- Design tokens -------------------------------------------------------------
PANEL_BG = "#121821"
GRID_COLOR = "rgba(148, 163, 184, 0.18)"
TEXT_PRIMARY = "#E6EEF8"
TEXT_SECONDARY = "#9FB0C3"
ACCENT = "#57C7FF"
ECO_COLORS = {"A": "#7CC7FF", "B": "#7BE495", "C": "#F6C177", "D": "#F28DA6", "E": "#B9A5FF"}
BODY_FONT = "'Roboto Condensed', system-ui, sans-serif"
DISPLAY_FONT = "'Roboto Slab', Georgia, serif"

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

PANEL1_ECOS = ["B20", "C44", "C00", "B12", "A10"]
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


def _top5_by_volume(forecasts: pd.DataFrame) -> list[str]:
    actuals = forecasts[forecasts["is_forecast"] == False].copy()
    if actuals.empty or "actual" not in actuals.columns:
        return PANEL1_ECOS[:]

    top = actuals.groupby("eco")["actual"].count().nlargest(5).index.tolist()
    return top if top else PANEL1_ECOS[:]


def _build_panel1_figure(forecasts: pd.DataFrame) -> go.Figure:
    fig = go.Figure()
    top_ecos = _top5_by_volume(forecasts)

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
            fig.add_vline(
                x=brk.timestamp() * 1000,
                line=dict(color=color, dash="dot", width=1),
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

    for eco_cat, color in ECO_COLORS.items():
        sub = engine_df[engine_df["eco"].str.startswith(eco_cat)]
        if sub.empty:
            continue

        fig.add_trace(
            go.Scatter(
                x=sub["engine_cp"],
                y=sub["human_win_rate_2000"],
                mode="markers+text",
                name=f"ECO {eco_cat}",
                text=sub["eco"],
                textposition="top center",
                marker=dict(
                    color=color,
                    size=12,
                    opacity=0.85,
                    line=dict(width=1, color=PANEL_BG),
                ),
                hovertemplate="<b>%{text}</b><br>Engine cp: %{x}<br>Human win rate: %{y:.3f}<br><extra></extra>",
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

    fig.update_layout(
        title="Engine Delta: Human vs Engine Win Rate",
        xaxis_title="Engine centipawn score",
        yaxis_title="Human win rate (2000+)",
    )
    _apply_plotly_typography(fig, title_size=16)
    return fig


def _build_panel3_figure(forecasts: pd.DataFrame) -> go.Figure:
    fig = go.Figure()
    actuals = forecasts[forecasts["is_forecast"] == False].copy()
    if actuals.empty:
        _apply_plotly_typography(fig, title_size=16)
        return fig

    actuals["eco_group"] = actuals["eco"].str[0]
    pivot = (
        actuals.groupby(["eco_group", "rating_bracket"])["actual"].mean().unstack(fill_value=None)
        if "rating_bracket" in actuals.columns
        else actuals.groupby("eco_group")["actual"].mean().to_frame()
    )

    fig.add_trace(
        go.Heatmap(
            z=pivot.values,
            x=[str(c) for c in pivot.columns],
            y=list(pivot.index),
            colorscale="RdYlGn",
            zmid=0.50,
            colorbar=dict(title="Win rate", tickfont=dict(color=TEXT_SECONDARY)),
        )
    )

    fig.update_layout(
        title="Average White Win Rate by ECO Family & Rating",
        xaxis_title="Rating bracket",
        yaxis_title="ECO family",
    )
    _apply_plotly_typography(fig, title_size=16)
    return fig


def _load_findings_json() -> dict | None:
    try:
        with open(FINDINGS_JSON, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _nav_html(current: str) -> str:
    pages = [
        ("index.html", "Overview"),
        ("openings.html", "Openings"),
        ("families.html", "Families"),
    ]
    links = ""
    for href, label in pages:
        active = ' class="active"' if href == current else ""
        links += f'<a href="{href}"{active}>{label}</a>\n'

    return f"""
<nav id="main-nav">
  <span class="brand">OpenCast</span>
  {links}
</nav>
"""


def _page_shell(title: str, nav_fragment: str, body: str, head_extras: str = "") -> str:
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{title} — OpenCast</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Roboto+Condensed:ital,wght@0,300;0,400;0,500;0,700;1,300;1,400&family=Roboto+Slab:wght@300;400;600;700&display=swap" rel="stylesheet">
  <link rel="stylesheet" href="assets/shared.css">
    {head_extras}
</head>
<body style="background:{PANEL_BG}; color:{TEXT_PRIMARY}; font-family:{BODY_FONT}; margin:0;">
{nav_fragment}
<main style="padding:2rem;">
{body}
</main>
<script src="assets/nav.js"></script>
</body>
</html>
"""


def _serialize_openings_data(
    forecasts: pd.DataFrame,
    engine_df: pd.DataFrame,
    catalog: pd.DataFrame,
    findings_json: dict | None,
) -> dict[str, dict]:
    fallback_narrative = "No analysis available yet."
    per_opening = findings_json.get("per_opening", {}) if findings_json else {}

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
        serialized[eco] = {
            "name": name,
            "eco_group": eco[0] if eco else None,
            "model_tier": model_tier,
            "actuals": actuals,
            "forecast": forecast,
            "structural_breaks": structural_breaks,
            "engine_cp": engine_cp,
            "p_engine": p_engine,
            "human_win_rate": human_win_rate,
            "delta": delta,
            "interpretation": interpretation,
            "narrative": str(narrative) if narrative is not None else fallback_narrative,
        }

    return serialized


def render_opening_template() -> str:
    body = f"""
<h1 id="opening-title">Opening Detail</h1>
<p style="margin:0 0 1rem 0;">
  <a href="openings.html" style="color:{TEXT_SECONDARY}; text-decoration:none; font-size:0.85rem;">← All openings</a>
</p>
<div id="opening-narrative" class="narrative"><p></p></div>
<div id="opening-chart"></div>
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

function hexToRgba(hexColor, alpha) {{
  const h = hexColor.replace("#", "");
  const r = parseInt(h.slice(0, 2), 16);
  const g = parseInt(h.slice(2, 4), 16);
  const b = parseInt(h.slice(4, 6), 16);
  return `rgba(${{r}}, ${{g}}, ${{b}}, ${{alpha}})`;
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

  const narrativeEl = document.querySelector("#opening-narrative p");
  const narrative = opening.narrative || FALLBACK_NARRATIVE;
  narrativeEl.textContent = narrative;
  narrativeEl.style.color = narrative === FALLBACK_NARRATIVE ? TEXT_SECONDARY : TEXT_PRIMARY;

  const color = ECO_COLORS[(opening.eco_group || eco.charAt(0) || "").toUpperCase()] || "{ACCENT}";
  const actuals = opening.actuals || [];
  const forecasts = opening.forecast || [];

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
      type: "scatter",
    }});

    traces.push({{
      x: forecasts.map((d) => d.month).concat(forecasts.map((d) => d.month).slice().reverse()),
      y: forecasts.map((d) => d.upper).concat(forecasts.map((d) => d.lower).slice().reverse()),
      fill: "toself",
      fillcolor: hexToRgba(color, 0.12),
      line: {{ color: "rgba(0,0,0,0)" }},
      showlegend: false,
      name: "95% CI",
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

  Plotly.newPlot("opening-chart", traces, layout, {{ responsive: true }}).then(() => {{
    const shapes = (opening.structural_breaks || []).map((month) => ({{
      type: "line",
      x0: month,
      x1: month,
      y0: 0,
      y1: 1,
      yref: "paper",
      line: {{ color, dash: "dot", width: 1 }},
    }}));
    Plotly.relayout("opening-chart", {{ shapes }});
  }});

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
  }}
}}

init();
</script>
"""
    head_extras = '<script src="https://cdn.plot.ly/plotly-2.35.2.min.js"></script>'
    return _page_shell("Opening Detail", _nav_html("openings.html"), body, head_extras=head_extras)


# -- Page renderers ------------------------------------------------------------
def render_overview(
    forecasts: pd.DataFrame,
    engine_df: pd.DataFrame,
    findings_json: dict | None,
) -> str:
    """Render data/output/dashboard/index.html — 3-panel overview."""
    headline = ""
    if findings_json:
        panels = findings_json.get("panels", {})
        fc_insight = panels.get("forecast", {}).get("insight", "")
        ed_insight = panels.get("engine_delta", {}).get("insight", "")
        hm_insight = panels.get("heatmap", {}).get("insight", "")
        main_headline = findings_json.get("headline", "")

        def _widget(label: str, text: str) -> str:
            if not text:
                return ""
            return (
                f'<div class="insight-widget">'
                f'<span class="insight-label">{label}</span>'
                f'<p class="insight-text">{text}</p>'
                f"</div>"
            )

        headline = (
            f'<section class="headlines">'
            f'<h1 class="page-title">{main_headline}</h1>'
            + _widget("Forecasts", fc_insight)
            + _widget("Engine Delta", ed_insight)
            + _widget("Heatmap", hm_insight)
            + "</section>"
        )
    else:
        headline = '<h1 class="page-title">OpenCast Dashboard</h1>'

    fig1_html = _build_panel1_figure(forecasts).to_html(full_html=False, include_plotlyjs="cdn")
    fig2_html = _build_panel2_figure(engine_df).to_html(full_html=False, include_plotlyjs=False)
    fig3_html = _build_panel3_figure(forecasts).to_html(full_html=False, include_plotlyjs=False)

    body = (
        headline
        + '<section class="panel">'
        + "<h2>Win Rate Forecasts</h2>"
        + fig1_html
        + "</section>"
        + '<section class="panel">'
        + "<h2>Engine Delta</h2>"
        + fig2_html
        + "</section>"
        + '<section class="panel">'
        + "<h2>ECO Heatmap</h2>"
        + fig3_html
        + "</section>"
        + '<p style="text-align:right; color:'
        + TEXT_SECONDARY
        + '; font-size:0.8rem;">'
        + '<a href="openings.html" style="color:'
        + ACCENT
        + ';">-> Browse all openings</a>'
        + "</p>"
    )
    return _page_shell("Overview", _nav_html("index.html"), body)


def render_openings_table(
    forecasts: pd.DataFrame,
    engine_df: pd.DataFrame,
    catalog: pd.DataFrame,
) -> str:
    """Render data/output/dashboard/openings.html — sortable table of all openings."""
    rows_html = ""
    ecos = catalog["eco"].tolist()

    for eco in ecos:
        cat_row = catalog[catalog["eco"] == eco]
        name = cat_row["name"].values[0] if not cat_row.empty else eco
        tier = int(cat_row["model_tier"].values[0]) if not cat_row.empty else "-"
        eco_group = eco[0] if eco else "-"
        color = ECO_COLORS.get(eco_group, TEXT_PRIMARY)

        fc_eco = forecasts[forecasts["eco"] == eco]
        actuals = fc_eco[fc_eco["is_forecast"] == False].sort_values("month")
        last_wr = f"{actuals['actual'].iloc[-1]:.3f}" if not actuals.empty else "-"

        ed_row = engine_df[engine_df["eco"] == eco]
        delta = f"{ed_row['delta'].values[0]:+.3f}" if not ed_row.empty else "-"

        rows_html += (
            f'<tr data-eco="{eco}" tabindex="0" role="link" aria-label="Open {name} ({eco}) details">'
            f'<td><span style="color:{color}; font-weight:600;">{eco}</span></td>'
            f"<td>{name}</td>"
            f"<td>{tier}</td>"
            f"<td>{last_wr}</td>"
            f"<td>{delta}</td>"
            "</tr>\n"
        )

    table_html = f"""
<h1>All Openings</h1>
<table id="openings-table" class="data-table">
  <thead>
    <tr>
      <th>ECO</th><th>Name</th><th>Tier</th><th>Win Rate (last)</th><th>Engine Δ</th>
    </tr>
  </thead>
  <tbody>
    {rows_html}
  </tbody>
</table>
<p style="color:{TEXT_SECONDARY}; font-size:0.85rem; margin-top:1rem;">
  Click any row to view the per-opening detail page.
</p>
<script>
(() => {{
  const rows = document.querySelectorAll("#openings-table tbody tr[data-eco]");
  rows.forEach((row) => {{
    const eco = row.getAttribute("data-eco");
    const navigate = () => {{
      window.location.href = `opening.html?eco=${{encodeURIComponent(eco)}}`;
    }};
    row.addEventListener("click", navigate);
    row.addEventListener("keydown", (event) => {{
      if (event.key === "Enter" || event.key === " ") {{
        event.preventDefault();
        navigate();
      }}
    }});
  }});
}})();
</script>
"""
    return _page_shell("All Openings", _nav_html("openings.html"), table_html)


def render_families(forecasts: pd.DataFrame) -> str:
    """Render data/output/dashboard/families.html — ECO family summary."""
    actuals = forecasts[forecasts["is_forecast"] == False].copy()
    actuals["eco_group"] = actuals["eco"].str[0]

    rows_html = ""
    for group in sorted(ECO_COLORS):
        sub = actuals[actuals["eco_group"] == group]
        avg_wr = f"{sub['actual'].mean():.3f}" if not sub.empty else "-"
        n_ecos = sub["eco"].nunique() if not sub.empty else 0
        color = ECO_COLORS.get(group, TEXT_PRIMARY)
        rows_html += (
            "<tr>"
            f'<td><span style="color:{color}; font-weight:700; font-size:1.1rem;">{group}</span></td>'
            f"<td>{n_ecos}</td>"
            f"<td>{avg_wr}</td>"
            "</tr>\n"
        )

    body = f"""
<h1>ECO Families</h1>
<table class="data-table">
  <thead>
    <tr><th>Family</th><th>Openings tracked</th><th>Avg win rate</th></tr>
  </thead>
  <tbody>{rows_html}</tbody>
</table>
"""
    return _page_shell("Families", _nav_html("families.html"), body)


# -- Orchestrator --------------------------------------------------------------
def run_visualizer() -> None:
    os.makedirs(ASSETS_DIR, exist_ok=True)

    forecasts = _safe_read_forecasts()
    engine_df = pd.read_csv(ENGINE_CSV) if os.path.exists(ENGINE_CSV) else pd.DataFrame()
    catalog = pd.read_csv(CATALOG_CSV) if os.path.exists(CATALOG_CSV) else pd.DataFrame()
    findings = _load_findings_json()

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

    openings_data = _serialize_openings_data(forecasts, engine_df, catalog, findings)
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
