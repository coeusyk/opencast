import html as _html
from urllib.parse import quote

import pandas as pd

from ..charts import (
    PLOTLY_CDN_SCRIPT,
    _PLOTLY_CFG,
    _build_compare_families_figure,
    _build_sparkline_figure,
    _family_sparkline_series,
)
from ..data_access import _config_float
from ..tokens import TEXT_PRIMARY, TEXT_SECONDARY
from ..shell import _nav_html, _page_shell

# Issue spec colours (distinct from tokens.py Plotly palette — do not merge)
FAMILY_COLORS: dict[str, str] = {
    "A": "#7B9FFF",
    "B": "#4DA3A6",
    "C": "#E6A84A",
    "D": "#E07BA0",
    "E": "#A78BFA",
}

CLASSIFICATION_LABELS: dict[str, str] = {
    "A": "Flank Openings",
    "B": "Semi-Open Games",
    "C": "Open Games",
    "D": "Closed / Semi-Closed",
    "E": "Indian Defenses",
}

# ---------------------------------------------------------------------------
# Client-side JS — sparkline toggle + compare trace visibility (Plotly).
# Compare + sparklines use Plotly; Plotly CDN loaded by compare chart.
# ---------------------------------------------------------------------------
_FAMILIES_JS = r"""
(function() {
  const FAMILIES = ["A", "B", "C", "D", "E"];

  function resizeSparkline(mount) {
    const plot = mount && mount.querySelector(".plotly-graph-div");
    if (plot && typeof Plotly !== "undefined") {
      Plotly.Plots.resize(plot);
    }
  }

  document.querySelectorAll(".fc-sparkline-btn").forEach(btn => {
    btn.addEventListener("click", () => {
      const fam = btn.dataset.family;
      const mount = document.getElementById("sparkline-" + fam);
      if (!mount) return;
      const isOpen = mount.style.display !== "none";
      mount.style.display = isOpen ? "none" : "block";
      btn.textContent = isOpen ? "Show sparkline ↓" : "Hide sparkline ↑";
      if (!isOpen) {
        requestAnimationFrame(() => resizeSparkline(mount));
      }
    });
  });

  const plotDiv = document.getElementById("compare-chart-plot");
  if (!plotDiv || typeof Plotly === "undefined") return;

  const active = new Set(FAMILIES);
  FAMILIES.forEach(fam => {
    const btn = document.getElementById("toggle-fam-" + fam);
    if (!btn) return;
    btn.addEventListener("click", () => {
      if (active.has(fam)) {
        if (active.size > 1) {
          active.delete(fam);
          btn.classList.remove("active");
        }
      } else {
        active.add(fam);
        btn.classList.add("active");
      }
      Plotly.restyle(plotDiv, {visible: FAMILIES.map(f => active.has(f))});
    });
  });
})();
"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _esc(value: object) -> str:
    return _html.escape(str(value), quote=True)


def _fmt_pct(value: float | None) -> str:
    return f"{value * 100:.2f}%" if value is not None else "—"


def _fmt_wr_range(min_wr: float | None, max_wr: float | None) -> str:
    if min_wr is None or max_wr is None:
        return "—"
    return f"{min_wr * 100:.2f}% – {max_wr * 100:.2f}%"


def _family_win_rate_bar_height(value: float) -> float:
    y_min = _config_float("dashboard_win_rate_axis_min", 0.46)
    y_max = _config_float("dashboard_win_rate_axis_max", 0.54)
    span = y_max - y_min
    if span <= 0:
        return 0.0
    return max(0.0, min(100.0, (value - y_min) / span * 100))


def _family_winrate_chart_title(group_vals: dict[str, float]) -> str:
    if len(group_vals) < 2:
        return "Win rate by ECO family"
    lowest_fam = min(group_vals, key=group_vals.get)
    return f"Family {lowest_fam} has the lowest win rate across all openings"


def _build_family_win_rate_css_chart(group_vals: dict[str, float]) -> str:
    """Pure CSS bar chart — mean per-ECO win rate per family (same source as family cards)."""
    chart_title = _family_winrate_chart_title(group_vals)

    bar_cols: list[str] = []
    for fam in sorted(FAMILY_COLORS):
        color = FAMILY_COLORS[fam]
        val = group_vals.get(fam)
        if val is not None:
            height = _family_win_rate_bar_height(val)
            val_text = f"{val * 100:.1f}%"
        else:
            height = 0.0
            val_text = "—"
        bar_cols.append(
            f'<div class="fam-bar-col">'
            f'<div class="fam-bar-stack">'
            f'<div class="fam-bar-unit" style="height:{height:.2f}%">'
            f'<span class="fam-bar-value">{_esc(val_text)}</span>'
            f'<div class="fam-bar-fill" style="background:{color}"></div>'
            f"</div>"
            f"</div>"
            f'<span class="fam-bar-letter">{_esc(fam)}</span>'
            f"</div>"
        )

    return (
        f'<div class="engine-box fam-winrate-box">'
        f'<p class="families-section-title fam-winrate-title">{_esc(chart_title)}</p>'
        f'<div class="fam-winrate-chart">'
        f'<div class="fam-winrate-bars-area">'
        f'<div class="fam-winrate-refline" aria-hidden="true"></div>'
        f'<div class="fam-winrate-bars">{"".join(bar_cols)}</div>'
        f"</div>"
        f"</div>"
        f"</div>"
    )


def _fmt_delta(value: float | None) -> str:
    if value is None:
        return "—"
    color = "#7BE495" if value > 0.005 else "#F28DA6" if value < -0.005 else TEXT_SECONDARY
    sign = "+" if value >= 0 else ""
    weight = "700" if abs(value) > 0.005 else "500"
    return f'<span style="color:{color};font-weight:{weight}">{sign}{value * 100:.2f} pp</span>'


def _tier_chips(counts: dict[int, int]) -> str:
    parts = []
    for tier, cls in ((1, "fc-tier-chip-1"), (2, "fc-tier-chip-2"), (3, "fc-tier-chip-3")):
        n = counts.get(tier, 0)
        if n:
            parts.append(
                f'<span class="fc-tier-chip {cls}">'
                f'<span class="fc-tier-label">T{tier}</span>'
                f'<span class="fc-tier-num">{n}</span>'
                f'</span>'
            )
    return "".join(parts)


def _trend_pills(counts: dict[str, int]) -> str:
    parts = []
    if counts.get("rising", 0):
        parts.append(f'<span class="trend-pill trend-pill-rise" title="{counts["rising"]} rising">↑ {counts["rising"]}</span>')
    if counts.get("stable", 0):
        parts.append(f'<span class="trend-pill trend-pill-flat" title="{counts["stable"]} stable">→ {counts["stable"]}</span>')
    if counts.get("falling", 0):
        parts.append(f'<span class="trend-pill trend-pill-fall" title="{counts["falling"]} falling">↓ {counts["falling"]}</span>')
    return " ".join(parts) if parts else '<span style="color:var(--text-faint)">—</span>'


def _fmt_engine_gap(avg_delta: float | None) -> str:
    if avg_delta is None:
        return '<span style="color:var(--text-faint)">—</span>'
    threshold = 0.005
    gap_pp = abs(avg_delta * 100)
    if avg_delta > threshold:
        cls = "fc-engine-chip-pos"
        sign = "+"
    elif avg_delta < -threshold:
        cls = "fc-engine-chip-neg"
        sign = "−"
    else:
        cls = "fc-engine-chip-flat"
        sign = ""
    val = f"{sign}{gap_pp:.1f} pp"
    tip = "Average deviation between Stockfish evaluation and human win rate for this family. Negative = humans underperform the engine prediction."
    return f'<span class="fc-engine-chip {cls}" title="{_esc(tip)}">{_esc(val)}</span>'


def _forecast_confidence_chips(counts: dict[str, int]) -> str:
    chips = []
    for key, display, css in (
        ("high",   "high", "fc-conf-high"),
        ("medium", "med",  "fc-conf-med"),
        ("low",    "low",  "fc-conf-low"),
    ):
        n = counts.get(key, 0)
        if n > 0:
            chips.append(
                f'<span class="fc-conf-chip {css}">'
                f'<span class="fc-conf-label">{display}</span>'
                f'<span class="fc-conf-num">{n}</span>'
                f'</span>'
            )
    if not chips:
        return '<span style="color:var(--text-faint)">—</span>'
    return '<div class="fc-conf-chips">' + "".join(chips) + "</div>"


def _regime_changes_chip(count: int) -> str:
    tip = "Win-rate regime shifts detected. Often correspond to new engine-recommended lines entering human play."
    return (
        f'<div class="fc-regime-row">'
        f'<p class="fc-row-label">REGIME CHANGES</p>'
        f'<span class="fc-regime-chip" title="{_esc(tip)}">{count} detected</span>'
        f"</div>"
    )


def _family_card(item: dict, sparkline_html: str = "") -> str:
    group = item["group"]
    color = FAMILY_COLORS.get(group, TEXT_PRIMARY)
    label = CLASSIFICATION_LABELS.get(group, "")
    n_ecos = item["n_ecos"]

    header = (
        f'<div class="fc-header">'
        f'<div class="fc-header-left">'
        f'<span class="fc-badge" style="--badge-color:{color}">{_esc(group)}</span>'
        f'<div class="fc-header-titles">'
        f'<p class="fc-eco-name">ECO {_esc(group)}</p>'
        f'<p class="fc-opening-count">{n_ecos} openings</p>'
        f'<p class="fc-classification">{_esc(label)}</p>'
        f'</div>'
        f'</div>'
        f'<div class="fc-tier-chips">{_tier_chips(item["tier_counts"])}</div>'
        f"</div>"
    )

    accent_bar = f'<div class="fc-bar" style="background:color-mix(in srgb,{color} 22%,transparent)"></div>'

    wr_row = (
        f'<div class="fc-wr-row">'
        f'<p class="fc-wr-label">AVG WIN RATE</p>'
        f'<p class="fc-wr-value">{_fmt_pct(item["avg_wr"])}</p>'
        f'<p class="fc-wr-range">{_fmt_wr_range(item["min_wr"], item["max_wr"])}</p>'
        f"</div>"
    )

    trends_row = (
        f'<div class="fc-trends-row">'
        f'<p class="fc-row-label">TRENDS</p>'
        f'<div>{_trend_pills(item["trend_counts"])}</div>'
        f"</div>"
    )

    engine_row = (
        f'<div class="fc-engine-row">'
        f'<p class="fc-row-label">ENGINE GAP</p>'
        f'{_fmt_engine_gap(item.get("avg_delta"))}'
        f"</div>"
    )

    confidence_row = (
        f'<div class="fc-confidence-row">'
        f'<p class="fc-row-label">FORECAST CONFIDENCE</p>'
        f'{_forecast_confidence_chips(item.get("forecast_quality_counts", {}))}'
        f"</div>"
    )

    regime_html = ""
    if item.get("regime_changes", 0) > 0:
        regime_html = _regime_changes_chip(item["regime_changes"])

    outlier_html = '<span style="color:var(--text-faint)">—</span>'
    if item.get("top_eco"):
        top_eco = str(item["top_eco"])
        top_name = str(item["top_name"] if item["top_name"] else item["top_eco"])
        top_delta = item.get("top_delta")
        pos = top_delta is not None and top_delta > 0.005
        neg = top_delta is not None and top_delta < -0.005
        badge_cls = "fc-outlier-badge-pos" if pos else "fc-outlier-badge-neg" if neg else "fc-outlier-badge-flat"
        outlier_html = (
            f'<a href="opening.html?eco={quote(top_eco)}" class="fc-outlier-box">'
            f'<span class="fc-outlier-badge {badge_cls}">{_esc(top_eco)}</span>'
            f'<div class="fc-outlier-body">'
            f'<div class="family-outlier-name" title="{_esc(top_name)}">{_esc(top_name)}</div>'
            f'<div class="family-outlier-delta">{_fmt_delta(item["top_delta"])}</div>'
            f"</div></a>"
        )

    outlier_row = (
        f'<div class="fc-outlier-row">'
        f'<p class="fc-row-label">TOP OUTLIER</p>'
        f'{outlier_html}'
        f"</div>"
    )

    sparkline = (
        f'<button class="fc-sparkline-btn" id="sparkline-btn-{_esc(group)}"'
        f' data-family="{_esc(group)}">Show sparkline ↓</button>'
        f'<div class="sparkline-mount" id="sparkline-{_esc(group)}" style="display:none">'
        f'{sparkline_html}'
        f"</div>"
    )

    return (
        f'<div class="family-card" style="--fam-color:{color}">'
        f'{header}{accent_bar}{wr_row}{trends_row}'
        f'{engine_row}{confidence_row}{regime_html}{outlier_row}'
        f'{sparkline}'
        f"</div>"
    )


# ---------------------------------------------------------------------------
# Main renderer
# ---------------------------------------------------------------------------

def render_families(
    forecasts: pd.DataFrame,
    engine_df: pd.DataFrame | None = None,
    catalog: pd.DataFrame | None = None,
    openings_data: dict | None = None,
) -> str:
    """Render data/output/dashboard/families.html."""
    actuals = forecasts[forecasts["is_forecast"] == False].copy()
    if not actuals.empty:
        actuals["eco_group"] = actuals["eco"].astype(str).str[0]
    else:
        actuals = pd.DataFrame(columns=["eco_group", "eco", "actual"])

    engine_df    = engine_df    if engine_df    is not None and not engine_df.empty    else pd.DataFrame()
    catalog      = catalog      if catalog      is not None and not catalog.empty      else pd.DataFrame()
    openings_data = openings_data or {}

    family_catalog: dict[str, pd.DataFrame] = {}
    if not catalog.empty and "eco" in catalog.columns:
        cat_groups = catalog["eco"].astype(str).str[0]
        for group, grp in catalog.assign(eco_group=cat_groups).groupby("eco_group"):
            family_catalog[str(group)] = grp.copy()

    summary = []
    for group in sorted(FAMILY_COLORS):
        family_actuals    = actuals[actuals["eco_group"] == group].copy()
        family_mean_by_eco = (
            family_actuals.groupby("eco")["actual"].mean()
            if not family_actuals.empty else pd.Series(dtype=float)
        )
        family_catalog_rows = family_catalog.get(group, pd.DataFrame())
        family_openings = (
            int(family_catalog_rows["eco"].nunique())
            if not family_catalog_rows.empty
            else int(family_actuals["eco"].nunique())
        )

        avg_wr = float(family_mean_by_eco.mean()) if not family_mean_by_eco.empty else None
        min_wr = float(family_mean_by_eco.min())  if not family_mean_by_eco.empty else None
        max_wr = float(family_mean_by_eco.max())  if not family_mean_by_eco.empty else None

        tier_counts = {1: 0, 2: 0, 3: 0}
        if not family_catalog_rows.empty and "model_tier" in family_catalog_rows.columns:
            tiers = pd.to_numeric(family_catalog_rows["model_tier"], errors="coerce")
            for t in (1, 2, 3):
                tier_counts[t] = int((tiers == t).sum())

        trend_counts = {"rising": 0, "stable": 0, "falling": 0}
        fq_counts    = {"high": 0, "medium": 0, "low": 0}
        regime_total = 0
        family_deltas: list[float] = []

        for eco, opening in openings_data.items():
            if not str(eco).startswith(group):
                continue
            direction = str(opening.get("trend_direction", "stable")).lower()
            if direction in trend_counts:
                trend_counts[direction] += 1
            fq = str(opening.get("forecast_quality", "") or "").lower()
            if fq in fq_counts:
                fq_counts[fq] += 1
            breaks = opening.get("structural_breaks", [])
            regime_total += len(breaks) if isinstance(breaks, list) else 0
            d = opening.get("delta")
            if d is not None:
                try:
                    family_deltas.append(float(d))
                except (TypeError, ValueError):
                    pass

        avg_delta = sum(family_deltas) / len(family_deltas) if family_deltas else None

        top_eco = top_name = top_delta = None
        if not engine_df.empty and "delta" in engine_df.columns and "eco" in engine_df.columns:
            family_engine = (
                engine_df[engine_df["eco"].astype(str).str.startswith(group)]
                .copy().dropna(subset=["delta"])
            )
            if not family_engine.empty:
                top_pos  = int(family_engine["delta"].abs().to_numpy().argmax())
                top_row  = family_engine.iloc[top_pos]
                top_eco  = str(top_row["eco"])
                tv       = pd.to_numeric(top_row["delta"], errors="coerce")
                top_delta = float(tv) if pd.notna(tv) else None
                if not catalog.empty and {"eco", "name"}.issubset(catalog.columns):
                    cat_row = catalog[catalog["eco"].astype(str) == top_eco]
                    if not cat_row.empty:
                        top_name = str(cat_row["name"].iloc[0])
                top_name = top_name or top_eco

        summary.append({
            "group":                  group,
            "n_ecos":                 family_openings,
            "avg_wr":                 avg_wr,
            "min_wr":                 min_wr,
            "max_wr":                 max_wr,
            "tier_counts":            tier_counts,
            "trend_counts":           trend_counts,
            "top_eco":                top_eco,
            "top_name":               top_name,
            "top_delta":              top_delta,
            "avg_delta":              avg_delta,
            "forecast_quality_counts": fq_counts,
            "regime_changes":         regime_total,
        })

    family_winrate_chart_html = _build_family_win_rate_css_chart({
        item["group"]: item["avg_wr"]
        for item in summary
        if item.get("avg_wr") is not None
    })

    total_ecos    = sum(item["n_ecos"] for item in summary)
    weighted_mean = (
        sum((item["avg_wr"] or 0.0) * item["n_ecos"] for item in summary) / total_ecos
        if total_ecos > 0 else None
    )
    total_rising  = sum(item["trend_counts"]["rising"] for item in summary)
    mean_text     = f"{weighted_mean * 100:.2f}%" if weighted_mean is not None else "—"

    # Avg Engine Gap hero tile
    all_deltas: list[float] = [
        float(d["delta"])
        for d in openings_data.values()
        if d.get("delta") is not None
    ]
    global_avg_abs    = sum(abs(d) for d in all_deltas) / len(all_deltas) if all_deltas else None
    global_avg_signed = sum(all_deltas) / len(all_deltas) if all_deltas else None
    gap_color = (
        "#7BE495" if (global_avg_signed or 0) > 0.001
        else "#F28DA6" if (global_avg_signed or 0) < -0.001
        else TEXT_SECONDARY
    )
    gap_display = f"{global_avg_abs * 100:.2f} pp" if global_avg_abs is not None else "—"
    gap_tip = "Mean deviation between Stockfish win probability and human win rate across Tier-1 openings."

    card_parts: list[str] = []
    for item in summary:
        group = item["group"]
        color = FAMILY_COLORS.get(group, TEXT_PRIMARY)
        months, values = _family_sparkline_series(openings_data, group)
        if months and values:
            delta_pp = values[-1] - values[0]
            if delta_pp > 0.05:
                delta_color = "#7BE495"
            elif delta_pp < -0.05:
                delta_color = "#F28DA6"
            else:
                delta_color = TEXT_SECONDARY
            delta_sign = "+" if delta_pp >= 0 else ""
            delta_label = f"{delta_sign}{delta_pp:.1f}pp"
            sl_fig = _build_sparkline_figure(months, values, color)
            plot_html = sl_fig.to_html(
                full_html=False,
                include_plotlyjs=False,
                config=_PLOTLY_CFG,
                div_id=f"sparkline-plot-{group}",
            )
            sparkline_html = (
                f'<div class="sparkline-inner">'
                f'<span class="sparkline-delta" style="color:{delta_color}">'
                f"{_esc(delta_label)}</span>"
                f"{plot_html}"
                f"</div>"
            )
        else:
            sparkline_html = '<span class="chart-unavailable">No data</span>'
        card_parts.append(_family_card(item, sparkline_html))
    cards_html = "\n".join(card_parts)

    compare_fig = _build_compare_families_figure(openings_data)
    compare_chart_html = compare_fig.to_html(
        full_html=False,
        include_plotlyjs=False,
        config=_PLOTLY_CFG,
        div_id="compare-chart-plot",
    )

    # Compare panel toggle buttons (#42)
    compare_btns = "".join(
        f'<button class="compare-toggle-btn active" id="toggle-fam-{g}"'
        f' style="--fam-color:{FAMILY_COLORS[g]}">ECO {_esc(g)}</button>'
        for g in sorted(FAMILY_COLORS)
    )

    fam_css = f"""<style>
.families-shell {{ max-width: 1080px; margin: 0 auto; padding: 2rem 1.5rem 4rem; }}

/* ── Header + compact metrics bar (Figma layout) ───────────────────── */
.families-header-row {{
  display: flex;
  flex-wrap: wrap;
  align-items: flex-start;
  justify-content: space-between;
  gap: 1.25rem;
  margin-bottom: 1.75rem;
}}
.families-header-text {{ flex: 1; min-width: 220px; }}
.families-title   {{ margin: 0 0 0.5rem; font-size: 1.375rem; font-weight: 600; letter-spacing: -0.02em; }}
.families-subtitle {{ margin: 0; color: var(--text-secondary); font-size: 1.0625rem; line-height: 1.65; max-width: 52rem; }}
.families-metrics-bar {{
  display: flex;
  flex-wrap: wrap;
  gap: 1.5rem;
  background: var(--surface-raised);
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  padding: 0.875rem 1.25rem;
  flex-shrink: 0;
}}
.metric-tile {{ min-width: 5.5rem; }}
.metric-label  {{ margin: 0 0 0.3rem; font-size: 0.6875rem; color: var(--text-faint); text-transform: uppercase; letter-spacing: 0.08em; font-family: var(--font-brand); font-weight: 600; }}
.metric-value  {{ margin: 0; font-size: 1.375rem; font-weight: 700; line-height: 1; color: var(--text-primary); font-family: var(--font-brand); }}
.families-section-title {{ font-size: 1rem; font-weight: 600; color: var(--text-primary); margin: 0 0 1rem; }}

/* ── Family win-rate CSS bar chart ─────────────────────────────────── */
.fam-winrate-box {{ margin-bottom: 1.5rem; }}
.fam-winrate-title {{ margin-top: 0; }}
.fam-winrate-chart {{
  height: 280px;
  display: flex;
  flex-direction: column;
}}
.fam-winrate-bars-area {{
  flex: 1;
  position: relative;
  min-height: 0;
  padding-bottom: 1.25rem;
  box-sizing: border-box;
}}
.fam-winrate-refline {{
  position: absolute;
  left: 0;
  right: 0;
  bottom: calc(1.25rem + (100% - 1.25rem) * 0.5);
  border-top: 1px dashed var(--text-faint);
  pointer-events: none;
  z-index: 1;
}}
.fam-winrate-bars {{
  position: absolute;
  inset: 0;
  display: flex;
  flex-direction: row;
  align-items: flex-end;
  justify-content: center;
  gap: 2.25rem;
  padding: 0 1.5rem;
  z-index: 2;
}}
.fam-bar-col {{
  display: flex;
  flex-direction: column;
  align-items: center;
  height: 100%;
  flex: 0 0 auto;
  width: 34px;
}}
.fam-bar-stack {{
  flex: 1;
  width: 34px;
  display: flex;
  flex-direction: column;
  justify-content: flex-end;
  min-height: 0;
}}
.fam-bar-unit {{
  width: 100%;
  display: flex;
  flex-direction: column;
  justify-content: flex-end;
  position: relative;
  min-height: 2px;
}}
.fam-bar-value {{
  position: absolute;
  bottom: 100%;
  left: 50%;
  transform: translateX(-50%);
  margin-bottom: 8px;
  font-size: 11px;
  color: var(--text-primary);
  font-family: var(--font-brand);
  font-weight: 600;
  line-height: 1;
  white-space: nowrap;
}}
.fam-bar-fill {{
  width: 100%;
  flex: 1;
  min-height: 2px;
  border-radius: 3px 3px 0 0;
}}
.fam-bar-letter {{
  flex-shrink: 0;
  margin-top: 0.35rem;
  font-size: 11px;
  font-family: var(--font-brand);
  font-weight: 600;
  color: var(--text-secondary);
}}

/* ── Card grid ─────────────────────────────────────────────────────── */
.families-grid {{
  display: grid;
  grid-template-columns: repeat(6, 1fr);
  gap: 1rem;
  margin-bottom: 1.5rem;
  align-items: start;
}}
/* 3 cards top row; D + E centered on bottom row (desktop) */
.family-card:nth-child(1) {{ grid-column: 1 / span 2; }}
.family-card:nth-child(2) {{ grid-column: 3 / span 2; }}
.family-card:nth-child(3) {{ grid-column: 5 / span 2; }}
.family-card:nth-child(4) {{ grid-column: 2 / span 2; }}
.family-card:nth-child(5) {{ grid-column: 4 / span 2; }}
.family-card {{
  background:
    radial-gradient(ellipse 95% 70% at 100% 0%, color-mix(in srgb, var(--fam-color) 16%, transparent), transparent 68%),
    radial-gradient(ellipse 75% 55% at 0% 100%, color-mix(in srgb, var(--fam-color) 9%, transparent), transparent 62%),
    linear-gradient(168deg, color-mix(in srgb, var(--fam-color) 7%, var(--surface)) 0%, var(--surface) 52%);
  border: 1px solid color-mix(in srgb, var(--fam-color) 12%, var(--border));
  border-radius: var(--radius-md);
  overflow: hidden;
  display: flex;
  flex-direction: column;
}}

/* Card header */
.fc-header       {{ display: flex; flex-wrap: wrap; justify-content: space-between; align-items: flex-start; gap: 0.5rem; padding: 0.875rem 1rem 0.75rem; }}
.fc-header-left  {{ display: flex; align-items: flex-start; gap: 0.625rem; flex: 1 1 auto; min-width: 0; }}
.fc-badge        {{
  display: inline-flex; align-items: center; justify-content: center;
  width: 2.125rem; height: 2.125rem; border-radius: var(--radius-sm); flex-shrink: 0;
  background: color-mix(in srgb, var(--badge-color) 7%, transparent);
  border: 1.5px solid color-mix(in srgb, var(--badge-color) 19%, transparent);
  color: var(--badge-color);
  font-family: var(--font-brand); font-weight: 700; font-size: 0.875rem;
}}
.fc-header-titles  {{ display: flex; flex-direction: column; gap: 0.1rem; flex: 1; min-width: 9rem; }}
.fc-eco-name       {{ font-family: var(--font-brand); font-size: 0.8rem; font-weight: 600; color: var(--text-primary); margin: 0; line-height: 1.25; }}
.fc-opening-count  {{ font-family: var(--font-body); font-size: 0.72rem; color: var(--text-faint); margin: 0; line-height: 1.3; }}
.fc-classification {{ font-family: var(--font-body); font-size: 0.72rem; color: var(--text-secondary); margin: 0; line-height: 1.35; white-space: nowrap; }}
.fc-tier-chips   {{ display: flex; gap: 0.35rem; flex-wrap: nowrap; flex-shrink: 0; margin-left: auto; align-items: flex-start; }}
.fc-tier-chip    {{ display: inline-flex; align-items: center; gap: 0.2rem; padding: 0.08rem 0.4rem; border-radius: 999px; font-size: 0.7rem; font-family: var(--font-brand); white-space: nowrap; border: 1px solid; }}
.fc-tier-label   {{ font-weight: 500; }}
.fc-tier-num     {{ color: var(--text-primary); font-weight: 700; }}
.fc-tier-chip-1  {{ border-color: var(--accent-teal); background: rgba(77,163,166,0.12); }}
.fc-tier-chip-1 .fc-tier-label {{ color: var(--accent-teal); }}
.fc-tier-chip-2  {{ border-color: var(--border); background: transparent; }}
.fc-tier-chip-2 .fc-tier-label {{ color: var(--text-faint); }}
.fc-tier-chip-3  {{ border-color: var(--border); background: transparent; }}
.fc-tier-chip-3 .fc-tier-label {{ color: var(--text-faint); }}

/* Accent bar */
.fc-bar {{ height: 2px; margin: 0 0 0.75rem; }}

/* Win rate row */
.fc-wr-row       {{ padding: 0 1rem 0.75rem; border-bottom: 1px solid var(--border); }}
.fc-wr-label     {{ font-family: var(--font-brand); font-size: 0.6875rem; font-weight: 600; text-transform: uppercase; letter-spacing: 0.08em; color: var(--text-faint); margin: 0 0 0.15rem; }}
.fc-wr-value     {{ font-family: var(--font-brand); font-size: 1.75rem; font-weight: 700; color: var(--text-primary); line-height: 1; margin: 0; }}
.fc-wr-range     {{ margin: 2px 0 0; font-family: var(--font-body); font-size: 11px; color: var(--text-faint); line-height: 1.3; }}

/* Row label shared */
.fc-row-label {{ font-family: var(--font-brand); font-size: 0.6rem; font-weight: 600; text-transform: uppercase; letter-spacing: 0.08em; color: var(--text-faint); margin: 0 0 0.3rem; }}

/* Section rows inside cards */
.fc-trends-row, .fc-engine-row, .fc-confidence-row, .fc-regime-row, .fc-outlier-row {{
  padding: 0.6875rem 1rem;
  border-bottom: 1px solid var(--border);
}}
.trend-pill     {{ display: inline-block; margin: 0.06rem 0.1rem; padding: 0.12rem 0.44rem; border-radius: 4px; font-size: 0.6875rem; line-height: 1.2; white-space: nowrap; font-family: var(--font-brand); font-weight: 600; }}
.trend-pill-rise {{ color: #7BE495; background: rgba(123,228,149,0.12); }}
.trend-pill-flat {{ color: var(--text-faint); background: rgba(135,142,158,0.09); font-weight: 500; }}
.trend-pill-fall {{ color: #F28DA6; background: rgba(242,141,166,0.12); }}

/* Engine gap */
.fc-engine-chip {{ display: inline-flex; align-items: center; padding: 0.2rem 0.55rem; border-radius: 4px; font-family: var(--font-brand); font-size: 0.75rem; font-weight: 700; cursor: help; }}
.fc-engine-chip-pos {{ color: #7BE495; background: rgba(123,228,149,0.12); }}
.fc-engine-chip-neg {{ color: #F28DA6; background: rgba(242,141,166,0.12); }}
.fc-engine-chip-flat {{ color: var(--text-secondary); background: rgba(135,142,158,0.09); }}

/* Forecast confidence */
.fc-conf-chips  {{ display: flex; gap: 0.35rem; flex-wrap: wrap; }}
.fc-conf-chip   {{ display: inline-flex; align-items: center; gap: 0.3rem; padding: 0.12rem 0.44rem; border-radius: 999px; font-size: 0.6875rem; font-family: var(--font-brand); }}
.fc-conf-label  {{ font-weight: 500; }}
.fc-conf-num    {{ color: var(--text-primary); font-weight: 700; }}
.fc-conf-high   {{ background: rgba(123,228,149,0.12); }}
.fc-conf-high .fc-conf-label {{ color: #7BE495; }}
.fc-conf-med    {{ background: rgba(77,163,166,0.12); }}
.fc-conf-med .fc-conf-label  {{ color: var(--accent-teal); }}
.fc-conf-low    {{ background: rgba(135,142,158,0.09); }}
.fc-conf-low .fc-conf-label  {{ color: var(--text-faint); }}
.fc-conf-low .fc-conf-num    {{ color: var(--text-secondary); }}

/* Regime changes */
.fc-regime-chip {{ display: inline-flex; align-items: center; padding: 0.2rem 0.55rem; border-radius: 4px; font-size: 0.75rem; font-weight: 700; font-family: var(--font-brand); color: var(--accent); background: rgba(74,158,255,0.10); cursor: help; }}

/* Outlier row */
.fc-outlier-box {{ display: flex; gap: 0.5rem; align-items: flex-start; background: var(--surface-2); border: 1px solid var(--border); border-radius: 5px; padding: 0.55rem 0.7rem; text-decoration: none; }}
.fc-outlier-box:hover {{ border-color: var(--border-strong); }}
.fc-outlier-badge {{ font-size: 0.625rem; font-family: var(--font-brand); font-weight: 600; letter-spacing: 0.04em; border-radius: 4px; padding: 0.12rem 0.38rem; flex-shrink: 0; }}
.fc-outlier-badge-pos {{ color: #7BE495; background: rgba(123,228,149,0.12); }}
.fc-outlier-badge-neg {{ color: #F28DA6; background: rgba(242,141,166,0.12); }}
.fc-outlier-badge-flat {{ color: var(--text-secondary); background: rgba(135,142,158,0.09); }}
.fc-outlier-body {{ min-width: 0; }}
.family-outlier-name  {{ color: var(--text-primary); font-size: 0.75rem; font-weight: 500; line-height: 1.35; overflow: hidden; white-space: nowrap; text-overflow: ellipsis; }}
.family-outlier-delta {{ margin-top: 0.2rem; font-size: 0.75rem; }}

/* Sparkline (#42) */
.fc-sparkline-btn {{
  display: block; width: 100%; margin: 0; padding: 0.625rem 1rem;
  font-family: var(--font-brand); font-size: 0.72rem; font-weight: 500;
  color: var(--text-secondary);
  background: rgba(255,255,255,0.03);
  border: none; border-top: 1px solid var(--border);
  cursor: pointer; text-align: left;
}}
.fc-sparkline-btn:hover {{ background: rgba(255,255,255,0.05); color: var(--text-primary); }}
.fc-sparkline-btn:active {{ background: rgba(255,255,255,0.07); }}
.sparkline-mount {{ min-height: 80px; padding: 0 0.5rem 0.75rem; }}
.sparkline-inner {{ position: relative; }}
.sparkline-delta {{
  position: absolute; top: 4px; right: 8px; z-index: 1;
  font-family: var(--font-brand); font-size: 11px; font-weight: 600;
}}
.chart-unavailable {{ font-size: 0.75rem; color: var(--text-faint); }}

/* Compare panel (#42) */
.compare-panel    {{ background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius-lg); padding: 1.25rem; margin-bottom: 1.5rem; }}
.compare-title    {{ font-family: var(--font-brand); font-size: 1rem; font-weight: 600; color: var(--text-primary); margin: 0 0 0.75rem; }}
.compare-toggles  {{ display: flex; gap: 0.5rem; flex-wrap: wrap; margin-bottom: 0.75rem; }}
.compare-toggle-btn {{
  padding: 0.25rem 0.75rem; border-radius: 999px; font-family: var(--font-brand);
  font-size: 0.8125rem; font-weight: 600; border: 1px solid var(--border);
  color: var(--text-faint); background: none; cursor: pointer; transition: all 150ms;
}}
.compare-toggle-btn.active {{
  background: color-mix(in srgb, var(--fam-color) 18%, transparent);
  border-color: var(--fam-color);
  color: var(--fam-color);
}}
#compare-chart {{ min-height: 240px; }}

/* Responsive */
@media (max-width: 1024px) {{
  .families-grid {{ grid-template-columns: repeat(2, 1fr); }}
  .family-card:nth-child(n) {{ grid-column: auto; }}
}}
@media (max-width: 768px)  {{
  .families-grid {{ grid-template-columns: 1fr; }}
  .families-shell {{ padding: 0.75rem 0.75rem 2.5rem; }}
  #compare-chart {{ min-height: 180px; }}
}}
</style>"""

    module_script = f"<script>{_FAMILIES_JS}</script>"

    body = f"""
<section class="families-shell">
  <section class="families-header-row">
    <div class="families-header-text">
      <h1 class="families-title">ECO Families</h1>
      <p class="families-subtitle">Family-level performance, tier mix, trend direction, and engine–human outliers across the tracked opening set.</p>
    </div>
    <div class="families-metrics-bar">
      <div class="metric-tile">
        <p class="metric-label">Tracked Openings</p>
        <p class="metric-value">{total_ecos}</p>
      </div>
      <div class="metric-tile">
        <p class="metric-label">Weighted Avg Win Rate</p>
        <p class="metric-value">{mean_text}</p>
      </div>
      <div class="metric-tile">
        <p class="metric-label">Rising Openings</p>
        <p class="metric-value" style="color:#7BE495">{total_rising}</p>
      </div>
      <div class="metric-tile">
        <p class="metric-label" title="{_esc(gap_tip)}">Avg Engine Gap</p>
        <p class="metric-value" style="color:{gap_color}">{_esc(gap_display)}</p>
      </div>
    </div>
  </section>

  {family_winrate_chart_html}

  <h2 class="families-section-title">Opening Families</h2>
  <div class="families-grid">
    {cards_html}
  </div>

  <div class="compare-panel">
    <p class="compare-title">Compare Families</p>
    <div class="compare-toggles">{compare_btns}</div>
    <div id="compare-chart">
      {compare_chart_html}
    </div>
  </div>
</section>
"""

    return _page_shell(
        "Families",
        _nav_html("families.html"),
        body,
        head_extras=PLOTLY_CDN_SCRIPT + fam_css,
        body_extras=module_script,
    )


def render_families_page(
    forecasts: pd.DataFrame,
    engine_df: pd.DataFrame | None = None,
    catalog: pd.DataFrame | None = None,
    openings_data: dict | None = None,
) -> str:
    return render_families(forecasts, engine_df=engine_df, catalog=catalog, openings_data=openings_data)
