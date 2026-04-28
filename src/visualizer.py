import os

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

_HERE = os.path.dirname(__file__)
FORECASTS_CSV   = os.path.join(_HERE, "..", "data", "output", "forecasts.csv")
DELTA_CSV       = os.path.join(_HERE, "..", "data", "output", "engine_delta.csv")
TS_CSV          = os.path.join(_HERE, "..", "data", "processed", "openings_ts.csv")
OUTPUT_HTML     = os.path.join(_HERE, "..", "data", "output", "dashboard.html")

# ── colour palette ──────────────────────────────────────────────────────────
ECO_COLORS = {
    "A": "#4C72B0",  # blue
    "B": "#DD8452",  # orange
    "C": "#55A868",  # green
    "D": "#C44E52",  # red
    "E": "#8172B3",  # purple
}

PANEL1_ECOS = ["B20", "C44", "C00", "B12", "A10"]  # fallback (overridden at runtime)
LINE_COLORS = ["#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd"]


def _top5_by_volume(ts: pd.DataFrame) -> list:
    """Return the 5 ECO codes with the highest total game count."""
    return ts.groupby("eco")["total"].sum().nlargest(5).index.tolist()


def _build_panel1(forecasts: pd.DataFrame, panel1_ecos: list) -> list:
    """Forecast + CI ribbon for top-5 openings. Returns list of traces."""
    traces = []
    for i, eco in enumerate(panel1_ecos):
        df = forecasts[forecasts["eco"] == eco].sort_values("month")
        name = df["opening_name"].iloc[0]
        color = LINE_COLORS[i]

        actual = df[~df["is_forecast"]]
        fcast  = df[df["is_forecast"]]

        # Actual line
        traces.append(go.Scatter(
            x=actual["month"], y=actual["actual"],
            mode="lines", name=f"{eco} {name}",
            line=dict(color=color, width=2),
            legendgroup=eco, showlegend=True,
            xaxis="x1", yaxis="y1",
        ))

        if not fcast.empty:
            # Confidence ribbon
            traces.append(go.Scatter(
                x=pd.concat([fcast["month"], fcast["month"][::-1]]),
                y=pd.concat([fcast["upper_ci"], fcast["lower_ci"][::-1]]),
                fill="toself",
                fillcolor=f"rgba({int(color[1:3],16)},{int(color[3:5],16)},{int(color[5:7],16)},0.15)",
                line=dict(color="rgba(255,255,255,0)"),
                hoverinfo="skip", showlegend=False,
                legendgroup=eco,
                xaxis="x1", yaxis="y1",
            ))
            # Forecast dashed line
            traces.append(go.Scatter(
                x=fcast["month"], y=fcast["forecast"],
                mode="lines", name=f"{eco} forecast",
                line=dict(color=color, width=2, dash="dash"),
                legendgroup=eco, showlegend=False,
                xaxis="x1", yaxis="y1",
            ))

        # Structural break annotations (vertical lines via shapes handled separately)
        breaks = actual[actual["structural_break"] == True]["month"].tolist()
        for bm in breaks:
            traces.append(go.Scatter(
                x=[bm, bm],
                y=[actual["actual"].min() * 0.99, actual["actual"].max() * 1.01],
                mode="lines",
                line=dict(color=color, width=1, dash="dot"),
                hovertemplate=f"{eco} structural break: {bm}<extra></extra>",
                showlegend=False, legendgroup=eco,
                xaxis="x1", yaxis="y1",
            ))

    return traces


def _build_panel2(delta: pd.DataFrame, ts: pd.DataFrame) -> list:
    """Bubble chart: engine cp vs human win rate."""
    volume = ts.groupby("eco")["total"].sum()
    delta = delta.copy()
    delta["volume"] = delta["eco"].map(volume)
    delta["eco_cat"] = delta["eco"].str[0]
    delta["color"] = delta["eco_cat"].map(ECO_COLORS)

    # Diagonal reference line: x from -100 to 100, y = sigmoid
    import math
    cp_range = list(range(-80, 81, 5))
    p_range = [1.0 / (1.0 + math.exp(-cp / 400)) for cp in cp_range]

    traces = [
        go.Scatter(
            x=cp_range, y=p_range,
            mode="lines", name="Engine expected",
            line=dict(color="#888888", width=1.5, dash="dot"),
            xaxis="x2", yaxis="y2",
        ),
        go.Scatter(
            x=delta["engine_cp"],
            y=delta["human_win_rate_2000"],
            mode="markers+text",
            text=delta["eco"],
            textposition="top center",
            marker=dict(
                size=delta["volume"] / delta["volume"].max() * 40 + 8,
                color=delta["color"],
                opacity=0.8,
                line=dict(width=1, color="white"),
            ),
            hovertemplate=(
                "<b>%{text}</b><br>"
                "Engine cp: %{x}<br>"
                "Human WR: %{y:.4f}<br>"
                "Delta: %{customdata:.4f}<extra></extra>"
            ),
            customdata=delta["delta"],
            name="Opening",
            showlegend=False,
            xaxis="x2", yaxis="y2",
        ),
    ]
    return traces


def _build_panel3(ts: pd.DataFrame) -> list:
    """ECO × month heatmap of average white_win_rate."""
    ts = ts.copy()
    ts["eco_cat"] = ts["eco"].str[0]
    pivot = ts.groupby(["month", "eco_cat"])["white_win_rate"].mean().reset_index()
    pivot_wide = pivot.pivot(index="eco_cat", columns="month", values="white_win_rate")

    traces = [go.Heatmap(
        z=pivot_wide.values,
        x=pivot_wide.columns.tolist(),
        y=pivot_wide.index.tolist(),
        colorscale=[
            [0.0,  "#C0392B"],
            [0.5,  "#FFFFFF"],
            [1.0,  "#27AE60"],
        ],
        zmid=0.50,
        zmin=0.46,
        zmax=0.54,
        colorbar=dict(title="White WR", x=1.01),
        hovertemplate="ECO cat: %{y}<br>Month: %{x}<br>Win rate: %{z:.4f}<extra></extra>",
        xaxis="x3", yaxis="y3",
    )]
    return traces


def run_visualizer() -> None:
    forecasts = pd.read_csv(FORECASTS_CSV)
    delta     = pd.read_csv(DELTA_CSV)
    ts        = pd.read_csv(TS_CSV)

    panel1_ecos = _top5_by_volume(ts)

    fig = make_subplots(
        rows=2, cols=2,
        row_heights=[0.55, 0.45],
        column_widths=[0.55, 0.45],
        specs=[
            [{"colspan": 2, "type": "xy"}, None],
            [{"type": "xy"},               {"type": "xy"}],
        ],
        subplot_titles=[
            "Win-Rate Forecasts — Top 5 Openings by Volume (95% CI)",
            "Engine Centipawn vs Human Win Rate",
            "ECO Category Win-Rate Heatmap (by Month)",
        ],
        vertical_spacing=0.12,
        horizontal_spacing=0.08,
    )

    for tr in _build_panel1(forecasts, panel1_ecos):
        fig.add_trace(tr, row=1, col=1)

    for tr in _build_panel2(delta, ts):
        fig.add_trace(tr, row=2, col=1)

    for tr in _build_panel3(ts):
        fig.add_trace(tr, row=2, col=2)

    fig.update_layout(
        title=dict(
            text="OpenCast — Chess Opening Analytics Dashboard",
            font=dict(size=22),
            x=0.5,
        ),
        height=900,
        template="plotly_white",
        legend=dict(
            orientation="v",
            x=1.02, y=0.98,
            borderwidth=1,
        ),
        font=dict(family="Inter, Arial, sans-serif", size=12),
    )

    fig.update_xaxes(title_text="Month", row=1, col=1, tickangle=-45)
    fig.update_yaxes(title_text="White Win Rate", row=1, col=1)
    fig.update_xaxes(title_text="Engine Centipawn (White advantage →)", row=2, col=1)
    fig.update_yaxes(title_text="Human Win Rate (2000 blitz)", row=2, col=1)
    fig.update_xaxes(title_text="Month", row=2, col=2, tickangle=-90, nticks=12)
    fig.update_yaxes(title_text="ECO Category", row=2, col=2)

    os.makedirs(os.path.dirname(OUTPUT_HTML), exist_ok=True)
    fig.write_html(OUTPUT_HTML, include_plotlyjs="cdn")
    print(f"Dashboard written → {OUTPUT_HTML}")


if __name__ == "__main__":
    run_visualizer()
