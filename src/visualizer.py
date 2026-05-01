import os
from datetime import datetime, timezone

import pandas as pd
import plotly.graph_objects as go

_HERE = os.path.dirname(__file__)
FORECASTS_CSV   = os.path.join(_HERE, "..", "data", "output", "forecasts.csv")
DELTA_CSV       = os.path.join(_HERE, "..", "data", "output", "engine_delta.csv")
TS_CSV          = os.path.join(_HERE, "..", "data", "processed", "openings_ts.csv")
OUTPUT_HTML     = os.path.join(_HERE, "..", "data", "output", "dashboard.html")

# Dashboard design tokens
PANEL_BG = "#121821"
GRID_COLOR = "rgba(148, 163, 184, 0.18)"
TEXT_PRIMARY = "#E6EEF8"
TEXT_SECONDARY = "#9FB0C3"
ACCENT = "#57C7FF"

ECO_COLORS = {
    "A": "#7CC7FF",
    "B": "#7BE495",
    "C": "#F6C177",
    "D": "#F28DA6",
    "E": "#B9A5FF",
}

PANEL1_ECOS = ["B20", "C44", "C00", "B12", "A10"]
LINE_COLORS = ["#57C7FF", "#7BE495", "#F6C177", "#F28DA6", "#B9A5FF"]

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
]

BODY_FONT = "'DM Sans', system-ui, sans-serif"
DISPLAY_FONT = "'DM Serif Display', Georgia, serif"


def _apply_plotly_typography(fig: go.Figure, title_size: int) -> None:
    fig.update_layout(
        font=dict(
            family=BODY_FONT,
            size=12,
        ),
        title=dict(
            font=dict(
                family=DISPLAY_FONT,
                size=title_size,
            )
        ),
    )
    if fig.layout.annotations:  # type: ignore[attr-defined]
        for annotation in fig.layout.annotations:  # type: ignore[attr-defined]
            annotation.font = dict(
                family=DISPLAY_FONT,
                size=14,
                color=annotation.font.color if annotation.font and annotation.font.color else TEXT_SECONDARY,
            )


def _safe_read_forecasts() -> pd.DataFrame:
    try:
        forecasts = pd.read_csv(
            FORECASTS_CSV,
            converters={
                "is_forecast": lambda value: str(value).strip().lower() == "true",
                "structural_break": lambda value: str(value).strip().lower() == "true",
            },
        )
    except pd.errors.EmptyDataError:
        forecasts = pd.DataFrame(columns=FORECAST_COLUMNS)

    if forecasts.empty:
        forecasts = pd.DataFrame(columns=FORECAST_COLUMNS)

    for col in FORECAST_COLUMNS:
        if col not in forecasts.columns:
            forecasts[col] = pd.Series(dtype="object")
    return forecasts


def _top5_by_volume(ts: pd.DataFrame) -> list:
    """Return the 5 ECO codes with the highest total game count."""
    if ts.empty:
        return PANEL1_ECOS
    return ts.groupby("eco")["total"].sum().nlargest(5).index.tolist()


def _build_panel1_figure(forecasts: pd.DataFrame, panel1_ecos: list) -> go.Figure:
    """Forecast + CI ribbon for top openings."""
    fig = go.Figure()
    has_series = False

    for i, eco in enumerate(panel1_ecos):
        df = forecasts[forecasts["eco"] == eco].sort_values("month")
        if df.empty:
            continue
        has_series = True
        name = df["opening_name"].iloc[0]
        color = LINE_COLORS[i]

        actual = df[~df["is_forecast"]]
        fcast  = df[df["is_forecast"]]

        if not actual.empty:
            fig.add_trace(go.Scatter(
                x=actual["month"], y=actual["actual"],
                mode="lines", name=f"{eco} {name}",
                line=dict(color=color, width=2.5),
                legendgroup=eco, showlegend=True,
                hovertemplate=(
                    f"<b>{eco} {name}</b><br>Month: %{{x}}"
                    "<br>Win rate: %{y:.3f}<extra></extra>"
                ),
            ))

        if not fcast.empty:
            fig.add_trace(go.Scatter(
                x=pd.concat([fcast["month"], fcast["month"][::-1]]),
                y=pd.concat([fcast["upper_ci"], fcast["lower_ci"][::-1]]),
                fill="toself",
                fillcolor=(
                    f"rgba({int(color[1:3], 16)},"
                    f"{int(color[3:5], 16)},"
                    f"{int(color[5:7], 16)},0.14)"
                ),
                line=dict(color="rgba(255,255,255,0)"),
                hoverinfo="skip", showlegend=False,
                legendgroup=eco,
            ))

            fig.add_trace(go.Scatter(
                x=fcast["month"], y=fcast["forecast"],
                mode="lines", name=f"{eco} forecast",
                line=dict(color=color, width=2, dash="dot"),
                legendgroup=eco, showlegend=False,
                hovertemplate=(
                    f"<b>{eco} forecast</b><br>Month: %{{x}}"
                    "<br>Forecast: %{y:.3f}<extra></extra>"
                ),
            ))

        if not actual.empty:
            breaks = actual[actual["structural_break"]]["month"].tolist()
            for bm in breaks:
                fig.add_vline(
                    x=bm,
                    line_width=1,
                    line_dash="dot",
                    line_color="rgba(196, 204, 216, 0.28)",
                )

    if not has_series:
        fig.add_annotation(
            text="No forecast series available yet",
            x=0.5,
            y=0.5,
            xref="paper",
            yref="paper",
            showarrow=False,
            font=dict(color=TEXT_SECONDARY, size=14),
        )

    fig.update_layout(
        title=dict(
            text="Win-Rate Forecasts (Top Openings by Volume)",
            x=0.0,
            y=0.97,
            font=dict(size=18, color=TEXT_PRIMARY),
        ),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor=PANEL_BG,
        margin=dict(l=58, r=28, t=70, b=56),
        height=500,
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.01,
            xanchor="left",
            x=0,
            font=dict(color=TEXT_SECONDARY, size=11),
            bgcolor="rgba(0,0,0,0)",
            itemclick="toggle",
        ),
        hoverlabel=dict(
            bgcolor="#111923",
            bordercolor="#2B3747",
            font=dict(color=TEXT_PRIMARY, size=12),
        ),
    )
    _apply_plotly_typography(fig, 18)
    fig.update_xaxes(
        title_text="Month",
        tickangle=-35,
        gridcolor=GRID_COLOR,
        linecolor="rgba(148, 163, 184, 0.34)",
        tickfont=dict(color=TEXT_SECONDARY),
        title_font=dict(color=TEXT_SECONDARY),
    )
    fig.update_yaxes(
        title_text="White win rate",
        tickformat=".1%",
        gridcolor=GRID_COLOR,
        linecolor="rgba(148, 163, 184, 0.34)",
        tickfont=dict(color=TEXT_SECONDARY),
        title_font=dict(color=TEXT_SECONDARY),
    )
    return fig


def _build_panel2_figure(delta: pd.DataFrame, ts: pd.DataFrame) -> go.Figure:
    """Bubble chart: engine cp vs human win rate."""
    fig = go.Figure()

    if delta.empty or ts.empty:
        fig.add_annotation(
            text="No engine-delta data available",
            x=0.5,
            y=0.5,
            xref="paper",
            yref="paper",
            showarrow=False,
            font=dict(color=TEXT_SECONDARY, size=14),
        )
        fig.update_layout(
            title=dict(text="Engine vs Human Performance", x=0.0, font=dict(color=TEXT_PRIMARY, size=16)),
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor=PANEL_BG,
            margin=dict(l=58, r=28, t=68, b=56),
            height=430,
        )
        _apply_plotly_typography(fig, 16)
        return fig

    volume = ts.groupby("eco")["total"].sum()
    delta = delta.copy()
    delta["volume"] = delta["eco"].map(volume)
    delta["eco_cat"] = delta["eco"].str[0]
    delta["color"] = delta["eco_cat"].map(ECO_COLORS)
    delta = delta.sort_values("volume", ascending=False)

    vol_min = float(delta["volume"].min())
    vol_max = float(delta["volume"].max())
    span = max(vol_max - vol_min, 1.0)
    delta["marker_size"] = 12 + ((delta["volume"] - vol_min) / span) ** 0.5 * 30

    label_ecos = set(delta.head(8)["eco"].tolist())
    delta["label"] = delta["eco"].where(delta["eco"].isin(label_ecos), "")

    import math
    cp_range = list(range(-80, 81, 5))
    p_range = [1.0 / (1.0 + math.exp(-cp / 400)) for cp in cp_range]

    fig.add_trace(go.Scatter(
        x=cp_range,
        y=p_range,
        mode="lines",
        name="Engine expected baseline",
        line=dict(color="rgba(230, 238, 248, 0.48)", width=1.8, dash="dot"),
        hovertemplate="Engine baseline<extra></extra>",
    ))

    fig.add_trace(go.Scatter(
        x=delta["engine_cp"],
        y=delta["human_win_rate_2000"],
        mode="markers+text",
        text=delta["label"],
        textposition="top center",
        textfont=dict(color="#DEE8F5", size=11),
        marker=dict(
            size=delta["marker_size"],
            color=delta["color"],
            opacity=0.88,
            line=dict(width=1.1, color="rgba(8, 11, 16, 0.85)"),
        ),
        customdata=delta[["eco", "opening_name", "delta", "volume"]],
        hovertemplate=(
            "<b>%{customdata[0]} - %{customdata[1]}</b>"
            "<br>Engine cp: %{x}"
            "<br>Human WR: %{y:.3f}"
            "<br>Delta: %{customdata[2]:+.4f}"
            "<br>Total games: %{customdata[3]:,.0f}<extra></extra>"
        ),
        name="Opening",
        showlegend=False,
    ))

    fig.update_layout(
        title=dict(
            text="Engine Centipawn vs Human Win Rate",
            x=0.0,
            y=0.96,
            font=dict(size=16, color=TEXT_PRIMARY),
        ),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor=PANEL_BG,
        margin=dict(l=58, r=24, t=68, b=56),
        height=430,
        hoverlabel=dict(
            bgcolor="#111923",
            bordercolor="#2B3747",
            font=dict(color=TEXT_PRIMARY, size=12),
        ),
    )
    _apply_plotly_typography(fig, 16)
    fig.update_xaxes(
        title_text="Engine centipawn (white advantage)",
        gridcolor=GRID_COLOR,
        zerolinecolor="rgba(230, 238, 248, 0.30)",
        linecolor="rgba(148, 163, 184, 0.34)",
        tickfont=dict(color=TEXT_SECONDARY),
        title_font=dict(color=TEXT_SECONDARY),
    )
    fig.update_yaxes(
        title_text="Human win rate (2000 blitz)",
        tickformat=".1%",
        gridcolor=GRID_COLOR,
        zerolinecolor="rgba(230, 238, 248, 0.30)",
        linecolor="rgba(148, 163, 184, 0.34)",
        tickfont=dict(color=TEXT_SECONDARY),
        title_font=dict(color=TEXT_SECONDARY),
    )
    return fig


def _build_panel3_figure(ts: pd.DataFrame) -> go.Figure:
    """ECO × month heatmap of average white_win_rate."""
    fig = go.Figure()

    if ts.empty:
        fig.add_annotation(
            text="No heatmap data available",
            x=0.5,
            y=0.5,
            xref="paper",
            yref="paper",
            showarrow=False,
            font=dict(color=TEXT_SECONDARY, size=14),
        )
        fig.update_layout(
            title=dict(text="ECO Category Heatmap", x=0.0, font=dict(color=TEXT_PRIMARY, size=16)),
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor=PANEL_BG,
            margin=dict(l=58, r=24, t=68, b=70),
            height=430,
        )
        _apply_plotly_typography(fig, 16)
        return fig

    ts = ts.copy()
    ts["eco_cat"] = ts["eco"].str[0]
    pivot = ts.groupby(["month", "eco_cat"])["white_win_rate"].mean().reset_index()
    pivot_wide = pivot.pivot(index="eco_cat", columns="month", values="white_win_rate")

    fig.add_trace(go.Heatmap(
        z=pivot_wide.values,
        x=pivot_wide.columns.tolist(),
        y=pivot_wide.index.tolist(),
        colorscale=[
            [0.0, "#1E3A8A"],
            [0.45, "#0F172A"],
            [0.50, "#334155"],
            [0.65, "#0E7490"],
            [1.0, "#34D399"],
        ],
        zmid=0.50,
        zmin=0.46,
        zmax=0.54,
        colorbar=dict(
            title=dict(text="White WR", font=dict(color=TEXT_SECONDARY)),
            x=1.02,
            thickness=12,
            tickcolor=TEXT_SECONDARY,
            tickfont=dict(color=TEXT_SECONDARY),
        ),
        hovertemplate="ECO cat: %{y}<br>Month: %{x}<br>Win rate: %{z:.4f}<extra></extra>",
    ))

    fig.update_layout(
        title=dict(
            text="ECO Category Heatmap by Month",
            x=0.0,
            y=0.96,
            font=dict(size=16, color=TEXT_PRIMARY),
        ),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor=PANEL_BG,
        margin=dict(l=58, r=24, t=68, b=70),
        height=430,
    )
    _apply_plotly_typography(fig, 16)
    fig.update_xaxes(
        title_text="Month",
        tickangle=-90,
        nticks=10,
        tickfont=dict(color=TEXT_SECONDARY),
        title_font=dict(color=TEXT_SECONDARY),
    )
    fig.update_yaxes(
        title_text="ECO category",
        tickfont=dict(color=TEXT_SECONDARY),
        title_font=dict(color=TEXT_SECONDARY),
    )
    return fig


def _build_dashboard_html(fig_forecast: go.Figure, fig_scatter: go.Figure, fig_heatmap: go.Figure,
                          last_month: str, generated_at: str) -> str:
    plot_config = {
        "displayModeBar": False,
        "responsive": True,
        "scrollZoom": False,
    }

    forecast_html = fig_forecast.to_html(full_html=False, include_plotlyjs="cdn", config=plot_config)
    scatter_html = fig_scatter.to_html(full_html=False, include_plotlyjs=False, config=plot_config)
    heatmap_html = fig_heatmap.to_html(full_html=False, include_plotlyjs=False, config=plot_config)

    return f"""<!doctype html>
<html lang=\"en\">
<head>
  <meta charset=\"utf-8\" />
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
  <title>OpenCast Dashboard</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=DM+Sans:ital,opsz,wght@0,9..40,300..700;1,9..40,300..700&family=DM+Serif+Display:ital@0;1&display=swap" rel="stylesheet">
  <style>
    :root {{
      --bg: #0B1017;
      --panel: #121821;
      --panel-strong: #162030;
      --text: #E6EEF8;
      --muted: #9FB0C3;
      --accent: #57C7FF;
      --border: #253246;
      --ring: rgba(87, 199, 255, 0.18);
    }}

    * {{ box-sizing: border-box; }}

    body {{
      margin: 0;
      background: radial-gradient(1200px 700px at 0% -10%, #132238 0%, var(--bg) 54%);
      color: var(--text);
            font-family: {BODY_FONT};
      -webkit-font-smoothing: antialiased;
      text-rendering: optimizeLegibility;
    }}

        body, .plotly-graph-div {{
            font-family: {BODY_FONT} !important;
        }}

        h1, .dashboard-title {{
            font-family: {DISPLAY_FONT} !important;
            font-weight: 400;
            letter-spacing: -0.01em;
        }}

        h2, h3, .panel-title {{
            font-family: {DISPLAY_FONT} !important;
            font-weight: 400;
        }}

        .meta-bar, .meta-tag, footer, .dashboard-footer, .meta, .pill, .footer-note {{
            font-family: {BODY_FONT} !important;
            font-weight: 300;
        }}

    .shell {{
      width: min(1320px, 94vw);
      margin: 28px auto 36px;
    }}

    .header {{
      padding: 22px 24px;
      border: 1px solid var(--border);
      border-radius: 14px;
      background: linear-gradient(180deg, rgba(22, 32, 48, 0.92) 0%, rgba(18, 24, 33, 0.95) 100%);
      box-shadow: 0 20px 40px rgba(0, 0, 0, 0.22);
    }}

    .eyebrow {{
      text-transform: uppercase;
      letter-spacing: 0.08em;
      color: var(--accent);
      font-size: 11px;
      margin-bottom: 10px;
      font-weight: 600;
    }}

    .header h1 {{
      margin: 0;
      font-size: clamp(1.5rem, 2.6vw, 2.2rem);
      line-height: 1.15;
            font-family: {DISPLAY_FONT};
      letter-spacing: 0.01em;
    }}

    .subtitle {{
      margin-top: 10px;
      color: var(--muted);
      font-size: 0.98rem;
      max-width: 78ch;
    }}

    .meta {{
      margin-top: 16px;
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
    }}

    .pill {{
      border: 1px solid var(--border);
      border-radius: 999px;
      padding: 6px 10px;
      font-size: 12px;
      color: var(--muted);
      background: rgba(10, 15, 22, 0.6);
    }}

    .grid {{
      margin-top: 18px;
      display: grid;
      gap: 16px;
      grid-template-columns: repeat(12, minmax(0, 1fr));
    }}

    .card {{
      border: 1px solid var(--border);
      border-radius: 14px;
      background: var(--panel);
      box-shadow: 0 12px 30px rgba(0, 0, 0, 0.2);
      padding: 12px;
      overflow: hidden;
    }}

    .card.hero {{
      grid-column: span 12;
      background: linear-gradient(180deg, rgba(24, 35, 52, 0.95) 0%, rgba(18, 24, 33, 0.98) 100%);
      border-color: #2A3B55;
      box-shadow: 0 16px 40px rgba(0, 0, 0, 0.28), inset 0 0 0 1px var(--ring);
    }}

    .card.half {{
      grid-column: span 6;
    }}

    .plot-wrap {{
      width: 100%;
      min-height: 320px;
    }}

    .plot-wrap .js-plotly-plot,
    .plot-wrap .plot-container,
    .plot-wrap .svg-container {{
      width: 100% !important;
    }}

    .footer-note {{
      margin-top: 12px;
      color: #7D8FA4;
      font-size: 12px;
      text-align: right;
    }}

    @media (max-width: 1024px) {{
      .shell {{ width: min(1100px, 96vw); }}
      .card.half {{ grid-column: span 12; }}
    }}

    @media (max-width: 640px) {{
      .shell {{ margin-top: 14px; }}
      .header {{ padding: 16px 16px; border-radius: 12px; }}
      .grid {{ gap: 12px; }}
      .card {{ padding: 8px; border-radius: 12px; }}
      .subtitle {{ font-size: 0.93rem; }}
      .footer-note {{ text-align: left; }}
    }}
  </style>
</head>
<body>
  <main class=\"shell\">
        <section class=\"header\">
      <div class=\"eyebrow\">OpenCast intelligence</div>
      <h1>Chess Opening Analytics Dashboard</h1>
      <p class=\"subtitle\">Monthly opening dynamics across practical play: forecast direction, engine-human gaps, and category-level momentum in one editorial analytics view.</p>
      <div class=\"meta\">
        <span class=\"pill\">Source: Lichess Opening Explorer</span>
        <span class=\"pill\">Rating focus: 2000 blitz</span>
        <span class=\"pill\">Latest complete month: {last_month}</span>
        <span class=\"pill\">Generated: {generated_at}</span>
      </div>
    </section>

    <section class=\"grid\">
      <article class=\"card hero\">
        <div class=\"plot-wrap\">{forecast_html}</div>
      </article>

      <article class=\"card half\">
        <div class=\"plot-wrap\">{scatter_html}</div>
      </article>

      <article class=\"card half\">
        <div class=\"plot-wrap\">{heatmap_html}</div>
      </article>
    </section>

    <div class=\"footer-note\">OpenCast dashboard · static HTML export for GitHub Pages</div>
  </main>
</body>
</html>
"""


def run_visualizer() -> None:
    forecasts = _safe_read_forecasts()
    delta     = pd.read_csv(DELTA_CSV)
    ts        = pd.read_csv(TS_CSV)

    panel1_ecos = _top5_by_volume(ts)

    fig_forecast = _build_panel1_figure(forecasts, panel1_ecos)
    fig_scatter = _build_panel2_figure(delta, ts)
    fig_heatmap = _build_panel3_figure(ts)

    latest_month = "n/a"
    if not ts.empty and "month" in ts.columns:
        latest_month = str(ts["month"].max())

    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    html = _build_dashboard_html(
        fig_forecast,
        fig_scatter,
        fig_heatmap,
        latest_month,
        generated_at,
    )

    os.makedirs(os.path.dirname(OUTPUT_HTML), exist_ok=True)
    with open(OUTPUT_HTML, "w", encoding="utf-8") as file:
        file.write(html)
    print(f"Dashboard written → {OUTPUT_HTML}")


if __name__ == "__main__":
    run_visualizer()
