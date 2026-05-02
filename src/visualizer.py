import json
import os
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

_HERE = os.path.dirname(__file__)
FORECASTS_CSV  = os.path.join(_HERE, "..", "data", "output", "forecasts.csv")
ENGINE_CSV     = os.path.join(_HERE, "..", "data", "output", "engine_delta.csv")
OUTPUT_HTML    = os.path.join(_HERE, "..", "data", "output", "dashboard.html")
FINDINGS_JSON  = os.path.join(_HERE, "..", "findings", "findings.json")

# ── Design tokens ─────────────────────────────────────────────────────────────
PANEL_BG       = "#121821"
GRID_COLOR     = "rgba(148, 163, 184, 0.18)"
TEXT_PRIMARY   = "#E6EEF8"
TEXT_SECONDARY = "#9FB0C3"
ACCENT         = "#57C7FF"
ECO_COLORS     = {"A": "#7CC7FF", "B": "#7BE495", "C": "#F6C177", "D": "#F28DA6", "E": "#B9A5FF"}

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
    "model_tier",
]

BODY_FONT    = "'DM Sans', system-ui, sans-serif"
DISPLAY_FONT = "'DM Serif Display', Georgia, serif"


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
    """Read forecasts.csv safely, returning an empty DataFrame on failure."""
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
    """Return up to 5 ECO codes with the highest total actual game volume."""
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
    """Panel 1: win rate forecast lines with CI shading and break annotations."""
    fig = go.Figure()
    top_ecos = _top5_by_volume(forecasts)

    for eco, color in zip(top_ecos, LINE_COLORS):
        grp = forecasts[forecasts["eco"] == eco].copy()
        if grp.empty:
            continue
        grp["month"] = pd.to_datetime(grp["month"])
        grp = grp.sort_values("month")

        actuals  = grp[grp["is_forecast"] == False]
        fc_rows  = grp[grp["is_forecast"] == True]

        # Actual line
        fig.add_trace(go.Scatter(
            x=actuals["month"], y=actuals["actual"],
            name=eco, mode="lines",
            line=dict(color=color, width=2),
        ))

        # Forecast line (dashed)
        if not fc_rows.empty:
            fig.add_trace(go.Scatter(
                x=fc_rows["month"], y=fc_rows["forecast"],
                name=f"{eco} forecast", mode="lines",
                line=dict(color=color, dash="dash", width=1.5),
                showlegend=False,
            ))
            # CI band
            fig.add_trace(go.Scatter(
                x=pd.concat([fc_rows["month"], fc_rows["month"].iloc[::-1]]),
                y=pd.concat([fc_rows["upper_ci"], fc_rows["lower_ci"].iloc[::-1]]),
                fill="toself",
                fillcolor=color.replace("#", "rgba(") + ",0.12)",
                line=dict(color="rgba(0,0,0,0)"),
                showlegend=False,
                name=f"{eco} CI",
            ))

        # Structural break lines
        breaks = actuals[actuals["structural_break"] == True]["month"]
        for brk in breaks:
            fig.add_vline(
                x=brk.timestamp() * 1000,
                line=dict(color=color, dash="dot", width=1),
            )

    fig.update_layout(title="Win Rate Forecast by Opening", xaxis_title="Month", yaxis_title="White Win Rate")
    _apply_plotly_typography(fig, title_size=16)
    return fig


def _build_panel2_figure(engine_df: pd.DataFrame) -> go.Figure:
    """Panel 2: engine delta bubble chart."""
    fig = go.Figure()

    if engine_df.empty:
        _apply_plotly_typography(fig, title_size=16)
        return fig

    for eco_cat, color in ECO_COLORS.items():
        sub = engine_df[engine_df["eco"].str.startswith(eco_cat)]
        if sub.empty:
            continue
        fig.add_trace(go.Scatter(
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
            hovertemplate=(
                "<b>%{text}</b><br>"
                "Engine cp: %{x}<br>"
                "Human win rate: %{y:.3f}<br>"
                "<extra></extra>"
            ),
        ))

    # Reference diagonal (engine-expected win rate)
    cp_range = list(range(-300, 301, 10))
    ref_probs = [1.0 / (1.0 + 10 ** (-cp / 400)) for cp in cp_range]
    fig.add_trace(go.Scatter(
        x=cp_range, y=ref_probs,
        mode="lines",
        name="Engine expected",
        line=dict(color=TEXT_SECONDARY, dash="dash", width=1),
    ))

    fig.update_layout(
        title="Engine Delta: Human vs Engine Win Rate",
        xaxis_title="Engine centipawn score",
        yaxis_title="Human win rate (2000+)",
    )
    _apply_plotly_typography(fig, title_size=16)
    return fig


def _build_panel3_figure(forecasts: pd.DataFrame) -> go.Figure:
    """Panel 3: ECO heatmap by rating bracket."""
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

    z    = pivot.values
    xlab = [str(c) for c in pivot.columns]
    ylab = list(pivot.index)

    fig.add_trace(go.Heatmap(
        z=z, x=xlab, y=ylab,
        colorscale="RdYlGn",
        zmid=0.50,
        colorbar=dict(title="Win rate", tickfont=dict(color=TEXT_SECONDARY)),
    ))

    fig.update_layout(
        title="Average White Win Rate by ECO Family & Rating",
        xaxis_title="Rating bracket",
        yaxis_title="ECO family",
    )
    _apply_plotly_typography(fig, title_size=16)
    return fig


def _load_findings_json() -> dict | None:
    try:
        with open(FINDINGS_JSON) as f:
            return json.load(f)
    except Exception:
        return None


def run_visualizer() -> None:
    forecasts  = _safe_read_forecasts()
    engine_df  = pd.read_csv(ENGINE_CSV) if os.path.exists(ENGINE_CSV) else pd.DataFrame()
    findings   = _load_findings_json()

    fig1 = _build_panel1_figure(forecasts)
    fig2 = _build_panel2_figure(engine_df)
    fig3 = _build_panel3_figure(forecasts)

    # Assemble 3-panel dashboard
    dashboard = make_subplots(
        rows=3, cols=1,
        subplot_titles=("Win Rate Forecasts", "Engine Delta", "ECO Heatmap"),
        vertical_spacing=0.10,
    )

    for trace in fig1.data:
        dashboard.add_trace(trace, row=1, col=1)
    for trace in fig2.data:
        dashboard.add_trace(trace, row=2, col=1)
    for trace in fig3.data:
        dashboard.add_trace(trace, row=3, col=1)

    dashboard.update_layout(
        height=1500,
        title_text="OpenCast Dashboard",
        title_font=dict(family=DISPLAY_FONT, size=22, color=TEXT_PRIMARY),
        plot_bgcolor=PANEL_BG,
        paper_bgcolor=PANEL_BG,
        font=dict(family=BODY_FONT, color=TEXT_PRIMARY),
        showlegend=True,
    )

    os.makedirs(os.path.dirname(OUTPUT_HTML), exist_ok=True)
    dashboard.write_html(OUTPUT_HTML, include_plotlyjs="cdn")
    print(f"Dashboard written \u2192 {OUTPUT_HTML}")


if __name__ == "__main__":
    run_visualizer()
