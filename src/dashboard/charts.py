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