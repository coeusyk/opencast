import json
import os
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go

_HERE = os.path.dirname(__file__)
FORECASTS_CSV = os.path.join(_HERE, "..", "data", "output", "forecasts.csv")
ENGINE_CSV    = os.path.join(_HERE, "..", "data", "output", "engine_delta.csv")
CATALOG_CSV   = os.path.join(_HERE, "..", "data", "openings_catalog.csv")
FINDINGS_JSON = os.path.join(_HERE, "..", "findings", "findings.json")
OUTPUT_DIR    = os.path.join(_HERE, "..", "data", "output", "dashboard")
ASSETS_DIR    = os.path.join(OUTPUT_DIR, "assets")

# ── Design tokens ─────────────────────────────────────────────────────────────
PANEL_BG       = "#121821"
GRID_COLOR     = "rgba(148, 163, 184, 0.18)"
TEXT_PRIMARY   = "#E6EEF8"
TEXT_SECONDARY = "#9FB0C3"
ACCENT         = "#57C7FF"
ECO_COLORS     = {"A": "#7CC7FF", "B": "#7BE495", "C": "#F6C177", "D": "#F28DA6", "E": "#B9A5FF"}
BODY_FONT      = "'DM Sans', system-ui, sans-serif"
DISPLAY_FONT   = "'DM Serif Display', Georgia, serif"

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
LINE_COLORS  = ["#57C7FF", "#7BE495", "#F6C177", "#F28DA6", "#B9A5FF"]


# ── Private helpers ──────────────────────────────────────────────────────────────
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
    except FileNotFoundError:
        return pd.DataFrame(columns=FORECAST_COLUMNS)
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
    top = (
        actuals.groupby("eco")["actual"]
        .count()
        .nlargest(5)
        .index.tolist()
    )
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
        fig.add_trace(go.Scatter(
            x=actuals["month"], y=actuals["actual"],
            name=eco, mode="lines",
            line=dict(color=color, width=2),
        ))
        if not fc_rows.empty:
            fig.add_trace(go.Scatter(
                x=fc_rows["month"], y=fc_rows["forecast"],
                name=f"{eco} forecast", mode="lines",
                line=dict(color=color, dash="dash", width=1.5),
                showlegend=False,
            ))
            fig.add_trace(go.Scatter(
                x=pd.concat([fc_rows["month"], fc_rows["month"].iloc[::-1]]),
                y=pd.concat([fc_rows["upper_ci"], fc_rows["lower_ci"].iloc[::-1]]),
                fill="toself",
                fillcolor=color.replace("#", "rgba(") + ",0.12)",
                line=dict(color="rgba(0,0,0,0)"),
                showlegend=False, name=f"{eco} CI",
            ))
        breaks = actuals[actuals["structural_break"] == True]["month"]
        for brk in breaks:
            fig.add_vline(
                x=brk.timestamp() * 1000,
                line=dict(color=color, dash="dot", width=1),
            )
    fig.update_layout(title="Win Rate Forecast by Opening",
                      xaxis_title="Month", yaxis_title="White Win Rate")
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
        fig.add_trace(go.Scatter(
            x=sub["engine_cp"], y=sub["human_win_rate_2000"],
            mode="markers+text", name=f"ECO {eco_cat}",
            text=sub["eco"], textposition="top center",
            marker=dict(color=color, size=12, opacity=0.85,
                        line=dict(width=1, color=PANEL_BG)),
            hovertemplate="<b>%{text}</b><br>Engine cp: %{x}<br>Human win rate: %{y:.3f}<br><extra></extra>",
        ))
    cp_range = list(range(-300, 301, 10))
    ref_probs = [1.0 / (1.0 + 10 ** (-cp / 400)) for cp in cp_range]
    fig.add_trace(go.Scatter(
        x=cp_range, y=ref_probs, mode="lines", name="Engine expected",
        line=dict(color=TEXT_SECONDARY, dash="dash", width=1),
    ))
    fig.update_layout(title="Engine Delta: Human vs Engine Win Rate",
                      xaxis_title="Engine centipawn score",
                      yaxis_title="Human win rate (2000+)")
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
        actuals.groupby(["eco_group", "rating_bracket"])["actual"]
        .mean()
        .unstack(fill_value=float("nan"))
        if "rating_bracket" in actuals.columns
        else actuals.groupby("eco_group")["actual"].mean().to_frame()
    )
    fig.add_trace(go.Heatmap(
        z=pivot.values, x=[str(c) for c in pivot.columns], y=list(pivot.index),
        colorscale="RdYlGn", zmid=0.50,
        colorbar=dict(title="Win rate", tickfont=dict(color=TEXT_SECONDARY)),
    ))
    fig.update_layout(title="Average White Win Rate by ECO Family & Rating",
                      xaxis_title="Rating bracket", yaxis_title="ECO family")
    _apply_plotly_typography(fig, title_size=16)
    return fig


def _load_findings_json() -> dict | None:
    try:
        with open(FINDINGS_JSON) as f:
            return json.load(f)
    except Exception:
        return None


def _nav_html(current: str) -> str:
    pages = [
        ("index.html",    "Overview"),
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


def _page_shell(title: str, nav_fragment: str, body: str) -> str:
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{title} — OpenCast</title>
  <link rel="stylesheet" href="assets/shared.css">
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


# ── Page renderers ──────────────────────────────────────────────────────────────
def render_overview(
    forecasts: pd.DataFrame,
    engine_df: pd.DataFrame,
    findings_json: dict | None,
) -> str:
    """Render data/output/dashboard/index.html — 3-panel overview."""
    # Headline widgets from findings.json
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
        + '<p style="text-align:right; color:' + TEXT_SECONDARY + '; font-size:0.8rem;">'
        + '<a href="openings.html" style="color:' + ACCENT + ';">→ Browse all openings</a>'
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

        # Last actual win rate
        fc_eco = forecasts[forecasts["eco"] == eco]
        actuals = fc_eco[fc_eco["is_forecast"] == False].sort_values("month")
        last_wr = f"{actuals['actual'].iloc[-1]:.3f}" if not actuals.empty else "—"

        # Engine delta
        ed_row = engine_df[engine_df["eco"] == eco]
        delta = f"{ed_row['delta'].values[0]:+.3f}" if not ed_row.empty else "—"

        rows_html += (
            f"<tr onclick=\"window.location='opening_{eco}.html'\">"
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
      <th>ECO</th><th>Name</th><th>Tier</th><th>Win Rate (last)</th><th>Engine \u0394</th>
    </tr>
  </thead>
  <tbody>
    {rows_html}
  </tbody>
</table>
<p style="color:{TEXT_SECONDARY}; font-size:0.85rem; margin-top:1rem;">
  Click any row to view the per-opening detail page.
</p>
"""
    return _page_shell("All Openings", _nav_html("openings.html"), table_html)


def render_families(forecasts: pd.DataFrame) -> str:
    """Render data/output/dashboard/families.html — ECO family summary."""
    actuals = forecasts[forecasts["is_forecast"] == False].copy()
    actuals["eco_group"] = actuals["eco"].str[0]

    rows_html = ""
    for group in sorted(ECO_COLORS):
        sub = actuals[actuals["eco_group"] == group]
        avg_wr   = f"{sub['actual'].mean():.3f}" if not sub.empty else "—"
        n_ecos   = sub["eco"].nunique() if not sub.empty else 0
        color    = ECO_COLORS.get(group, TEXT_PRIMARY)
        rows_html += (
            f"<tr>"
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


def render_opening_page(
    eco: str,
    forecasts: pd.DataFrame,
    engine_df: pd.DataFrame,
    findings_json: dict | None,
) -> str:
    """Render data/output/dashboard/opening_{eco}.html — per-opening detail."""
    fc_eco = forecasts[forecasts["eco"] == eco].copy()
    name = fc_eco["opening_name"].iloc[0] if not fc_eco.empty else eco

    # Per-opening narrative from findings.json
    # Expected findings.json shape when per-ECO analysis is available:
    # { "per_opening": { "B20": "narrative text...", ... } }
    per_opening = findings_json.get("per_opening", {}) if findings_json else {}
    narrative = per_opening.get(eco, "No analysis available yet.")

    fig = go.Figure()
    if not fc_eco.empty:
        fc_eco["month"] = pd.to_datetime(fc_eco["month"])
        fc_eco = fc_eco.sort_values("month")
        color = ECO_COLORS.get(eco[0], ACCENT)

        act = fc_eco[fc_eco["is_forecast"] == False]
        fc_rows = fc_eco[fc_eco["is_forecast"] == True]

        fig.add_trace(go.Scatter(
            x=act["month"], y=act["actual"],
            mode="lines", name="Actual",
            line=dict(color=color, width=2),
        ))
        if not fc_rows.empty:
            fig.add_trace(go.Scatter(
                x=fc_rows["month"], y=fc_rows["forecast"],
                mode="lines", name="Forecast",
                line=dict(color=color, dash="dash", width=1.5),
            ))
            fig.add_trace(go.Scatter(
                x=pd.concat([fc_rows["month"], fc_rows["month"].iloc[::-1]]),
                y=pd.concat([fc_rows["upper_ci"], fc_rows["lower_ci"].iloc[::-1]]),
                fill="toself",
                fillcolor=color.replace("#", "rgba(") + ",0.12)",
                line=dict(color="rgba(0,0,0,0)"),
                showlegend=False, name="95% CI",
            ))
        breaks = act[act["structural_break"] == True]["month"]
        for brk in breaks:
            fig.add_vline(x=brk.timestamp() * 1000,
                          line=dict(color=color, dash="dot", width=1))

    fig.update_layout(title=f"{eco} — {name}",
                      xaxis_title="Month", yaxis_title="White Win Rate")
    _apply_plotly_typography(fig, title_size=18)
    fig_html = fig.to_html(full_html=False, include_plotlyjs="cdn")

    # Engine delta summary
    ed_row = engine_df[engine_df["eco"] == eco]
    engine_html = ""
    if not ed_row.empty:
        cp    = int(ed_row["engine_cp"].values[0])
        p_eng = float(ed_row["p_engine"].values[0])
        human = float(ed_row["human_win_rate_2000"].values[0])
        delta = float(ed_row["delta"].values[0])
        interp = str(ed_row["interpretation"].values[0])
        engine_html = (
            f'<div class="engine-box">'
            f"<h3>Engine Evaluation</h3>"
            f"<p>Stockfish depth-20: <strong>{cp:+d} cp</strong> "
            f"\u2192 P(white wins) = {p_eng:.3f}</p>"
            f"<p>Human win rate (2000+): {human:.3f}</p>"
            f"<p>Delta: <strong>{delta:+.3f}</strong> — {interp}</p>"
            "</div>"
        )

    body = (
        f'<h1><a href="openings.html" style="color:{TEXT_SECONDARY}; "
        f'text-decoration:none; font-size:0.85rem;">← All openings</a> "
        f"{name} ({eco})</h1>\n"
        + f'<div class="narrative"><p>{narrative}</p></div>\n'
        + fig_html
        + "\n"
        + engine_html
    )
    return _page_shell(name, _nav_html(""), body)


# ── Orchestrator ───────────────────────────────────────────────────────────────────
def run_visualizer() -> None:
    os.makedirs(ASSETS_DIR, exist_ok=True)

    forecasts    = _safe_read_forecasts()
    engine_df    = pd.read_csv(ENGINE_CSV) if os.path.exists(ENGINE_CSV) else pd.DataFrame()
    catalog      = pd.read_csv(CATALOG_CSV) if os.path.exists(CATALOG_CSV) else pd.DataFrame()
    findings     = _load_findings_json()

    # Copy shared CSS + JS assets
    for asset_name in ("shared.css", "nav.js"):
        src = Path(__file__).parent / "assets" / asset_name
        dst = Path(ASSETS_DIR) / asset_name
        if src.exists():
            import shutil
            shutil.copy2(src, dst)

    # Render overview page
    overview_html = render_overview(forecasts, engine_df, findings)
    overview_path = os.path.join(OUTPUT_DIR, "index.html")
    Path(overview_path).write_text(overview_html, encoding="utf-8")
    print(f"Overview written \u2192 {overview_path}")

    # Render openings table
    if not catalog.empty:
        ot_html = render_openings_table(forecasts, engine_df, catalog)
        ot_path = os.path.join(OUTPUT_DIR, "openings.html")
        Path(ot_path).write_text(ot_html, encoding="utf-8")
        print(f"Openings table written \u2192 {ot_path}")

        # Render per-opening detail pages
        for eco in catalog["eco"].tolist():
            detail_html = render_opening_page(eco, forecasts, engine_df, findings)
            detail_path = os.path.join(OUTPUT_DIR, f"opening_{eco}.html")
            Path(detail_path).write_text(detail_html, encoding="utf-8")
        print(f"Per-opening pages written ({len(catalog)} ECOs)")

    # Render families page
    families_html = render_families(forecasts)
    families_path = os.path.join(OUTPUT_DIR, "families.html")
    Path(families_path).write_text(families_html, encoding="utf-8")
    print(f"Families page written \u2192 {families_path}")

    print(f"\nDashboard written \u2192 {OUTPUT_DIR}/")


if __name__ == "__main__":
    run_visualizer()
