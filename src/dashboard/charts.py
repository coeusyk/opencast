import pandas as pd
import plotly.graph_objects as go

from .tokens import (
    BODY_FONT,
    ECO_COLORS,
    GRID_COLOR,
    LINE_COLORS,
    PANEL_BG,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
    _apply_plotly_typography,
    _hex_to_rgba,
)


def _reps_by_max_delta(engine_df: pd.DataFrame) -> list[str]:
    """Pick one ECO per group (A-E) with the highest absolute engine delta."""
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
        legend=dict(
            orientation="h",
            x=0.5,
            y=-0.2,
            xanchor="center",
            yanchor="top",
            font=dict(size=11, color=TEXT_SECONDARY),
            bgcolor="rgba(0,0,0,0)",
            borderwidth=0,
            tracegroupgap=0,
        ),
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

    fig.add_hline(y=0.5, line=dict(color=GRID_COLOR, width=1, dash="dot"))
    fig.add_vline(x=0, line=dict(color=GRID_COLOR, width=1, dash="dot"))

    quadrants = [
        (-220, 0.537, "Humans overperform<br><i>practical play favoured</i>"),
        (220, 0.537, "Engine strength<br><i>well executed</i>"),
        (-220, 0.463, "Objectively weak<br><i>& underplayed</i>"),
        (220, 0.463, "Theory-dependent<br><i>advantage lost in play</i>"),
    ]
    for qx, qy, qtxt in quadrants:
        fig.add_annotation(
            x=qx,
            y=qy,
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
        legend=dict(
            orientation="h",
            x=0.5,
            y=-0.2,
            xanchor="center",
            yanchor="top",
            font=dict(size=11, color=TEXT_SECONDARY),
            bgcolor="rgba(0,0,0,0)",
            borderwidth=0,
            tracegroupgap=0,
        ),
    )
    _apply_plotly_typography(fig, title_size=16)
    return fig


def _build_panel3_figure(engine_df: pd.DataFrame) -> go.Figure:
    """Bar chart of avg human win rate per ECO family (A-E)."""
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


# Issue-spec family palette (Families / Engine pages — distinct from tokens ECO_COLORS)
FAMILY_ISSUE_COLORS: dict[str, str] = {
    "A": "#7B9FFF",
    "B": "#4DA3A6",
    "C": "#E6A84A",
    "D": "#E07BA0",
    "E": "#A78BFA",
}
_FAMILIES_ORDER = ["A", "B", "C", "D", "E"]
_PLOTLY_CFG = {"scrollZoom": False, "displayModeBar": False}


def _family_monthly_from_openings(openings_data: dict) -> dict[str, dict[str, dict[str, float]]]:
    """Aggregate mean win rate per family per month from openings_data actuals."""
    fm: dict[str, dict[str, dict[str, float]]] = {}
    for eco, d in openings_data.items():
        fam = str(d.get("eco_group") or (str(eco)[0] if eco else "") or "").upper()
        if not fam:
            continue
        if fam not in fm:
            fm[fam] = {}
        for pt in d.get("actuals") or []:
            wr = pt.get("win_rate")
            if wr is None:
                continue
            month = str(pt.get("month", ""))[:7]
            if not month:
                continue
            bucket = fm[fam].setdefault(month, {"s": 0.0, "n": 0})
            bucket["s"] += float(wr)
            bucket["n"] += 1
    return fm


def _flatten_regime_points(openings_data: dict) -> list[dict]:
    points: list[dict] = []
    for eco, d in openings_data.items():
        breaks = d.get("structural_breaks") or []
        if not isinstance(breaks, list):
            continue
        fam = str(d.get("eco_group") or (str(eco)[0] if eco else "") or "").upper()
        name = d.get("name") or eco
        engine_cp = d.get("engine_cp")
        for month in breaks:
            points.append({
                "eco": str(eco),
                "name": str(name),
                "family": fam,
                "month": str(month)[:7],
                "engine_cp": engine_cp,
            })
    return points


def _normalize_marker_sizes(cp_values: list[float], lo: float = 8.0, hi: float = 28.0) -> list[float]:
    if not cp_values:
        return []
    abs_vals = [abs(v) for v in cp_values]
    max_abs = max(abs_vals) if abs_vals else 1.0
    min_abs = min(abs_vals) if abs_vals else 0.0
    if max_abs == min_abs:
        return [(lo + hi) / 2] * len(cp_values)
    return [
        lo + (abs(v) - min_abs) / (max_abs - min_abs) * (hi - lo)
        for v in cp_values
    ]


def _build_regime_scatter_figure(openings_data: dict) -> go.Figure:
    """Structural break events scatter — family × month, bubble size ∝ |engine_cp|."""
    fig = go.Figure()
    points = _flatten_regime_points(openings_data)

    if not points:
        fig.add_annotation(
            text="No structural break data available.",
            xref="paper", yref="paper", x=0.5, y=0.5,
            showarrow=False,
            font=dict(color=TEXT_SECONDARY, size=12, family=BODY_FONT),
        )
        fig.update_layout(
            height=260,
            margin=dict(l=40, r=16, t=8, b=32),
            xaxis=dict(visible=False),
            yaxis=dict(visible=False),
        )
        _apply_plotly_typography(fig, title_size=16)
        return fig

    for fam in _FAMILIES_ORDER:
        fam_pts = [p for p in points if p["family"] == fam]
        if not fam_pts:
            continue
        x_vals = [pd.to_datetime(p["month"]) for p in fam_pts]
        y_vals = [fam] * len(fam_pts)
        cp_vals = [float(p["engine_cp"] or 0) for p in fam_pts]
        sizes = _normalize_marker_sizes(cp_vals)
        hover = [
            f"<b>{p['eco']}</b><br>{p['name']}<br>Month: {p['month']}<br>Engine cp: {p['engine_cp']}"
            for p in fam_pts
        ]
        color = FAMILY_ISSUE_COLORS.get(fam, TEXT_SECONDARY)
        fig.add_trace(
            go.Scatter(
                x=x_vals,
                y=y_vals,
                mode="markers",
                name=fam,
                marker=dict(
                    color=color,
                    size=sizes,
                    sizemode="diameter",
                    line=dict(width=0),
                    opacity=0.92,
                ),
                text=hover,
                hoverinfo="text",
                showlegend=False,
            )
        )

    fig.update_layout(
        height=260,
        margin=dict(l=36, r=16, t=8, b=36),
        yaxis=dict(
            categoryorder="array",
            categoryarray=["E", "D", "C", "B", "A"],
            tickfont=dict(size=10, color=TEXT_SECONDARY),
            gridcolor=GRID_COLOR,
            zeroline=False,
        ),
        xaxis=dict(
            tickformat="%y %m",
            tickfont=dict(size=10, color=TEXT_SECONDARY),
            gridcolor=GRID_COLOR,
            zeroline=False,
        ),
    )
    _apply_plotly_typography(fig, title_size=16)
    return fig


def _build_compare_families_figure(openings_data: dict) -> go.Figure:
    """Multi-family win-rate line chart — last 24 months."""
    fig = go.Figure()
    fm = _family_monthly_from_openings(openings_data)

    all_months = sorted({
        m for fam in _FAMILIES_ORDER for m in (fm.get(fam) or {})
    })
    months = all_months[-24:] if all_months else []
    x_vals = [pd.to_datetime(m) for m in months]

    for fam in _FAMILIES_ORDER:
        fam_data = fm.get(fam) or {}
        y_vals = []
        for m in months:
            bucket = fam_data.get(m)
            if bucket and bucket["n"]:
                y_vals.append(round(bucket["s"] / bucket["n"] * 10000) / 100)
            else:
                y_vals.append(None)
        color = FAMILY_ISSUE_COLORS.get(fam, TEXT_SECONDARY)
        fig.add_trace(
            go.Scatter(
                x=x_vals,
                y=y_vals,
                mode="lines",
                name=fam,
                line=dict(color=color, width=2),
                connectgaps=True,
                hovertemplate=f"Family {fam}<br>%{{x|%b %Y}}: %{{y:.1f}}%<extra></extra>",
            )
        )

    fig.add_hline(
        y=50,
        line=dict(color="rgba(255,255,255,0.2)", dash="dot", width=1),
    )
    fig.update_layout(
        height=240,
        margin=dict(l=40, r=16, t=8, b=32),
        yaxis=dict(range=[44, 56], ticksuffix="%", gridcolor=GRID_COLOR),
        xaxis=dict(gridcolor=GRID_COLOR, tickfont=dict(size=10)),
        showlegend=False,
    )
    _apply_plotly_typography(fig, title_size=16)
    return fig


def _build_sparkline_figure(months: list[str], values: list[float], color: str) -> go.Figure:
    """Compact area sparkline for a single ECO family."""
    fig = go.Figure()
    x_vals = [pd.to_datetime(m) for m in months]
    fig.add_trace(
        go.Scatter(
            x=x_vals,
            y=values,
            mode="lines",
            fill="tozeroy",
            fillcolor=_hex_to_rgba(color, alpha=0.08),
            line=dict(color=color, width=1.5),
            hovertemplate="%{x|%b %Y}: %{y:.1f}%<extra></extra>",
        )
    )
    fig.add_hline(
        y=50,
        line=dict(color="rgba(255,255,255,0.2)", dash="dot", width=1),
    )
    fig.update_layout(
        height=80,
        margin=dict(l=0, r=0, t=0, b=0),
        showlegend=False,
        plot_bgcolor=PANEL_BG,
        paper_bgcolor=PANEL_BG,
    )
    fig.update_xaxes(visible=False, fixedrange=True)
    fig.update_yaxes(visible=False, fixedrange=True)
    _apply_plotly_typography(fig, title_size=12)
    return fig


def _family_sparkline_series(
    openings_data: dict, group: str, n_months: int = 12,
) -> tuple[list[str], list[float]]:
    fm = _family_monthly_from_openings(openings_data)
    fam_data = fm.get(group.upper()) or {}
    months_out: list[str] = []
    values_out: list[float] = []
    for m in sorted(fam_data.keys())[-n_months:]:
        bucket = fam_data[m]
        if bucket["n"]:
            months_out.append(m)
            values_out.append(round(bucket["s"] / bucket["n"] * 10000) / 100)
    return months_out, values_out