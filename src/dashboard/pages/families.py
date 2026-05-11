import html as _html
from urllib.parse import quote

import pandas as pd

from ..charts import _build_panel3_figure
from ..tokens import ECO_COLORS, TEXT_PRIMARY, TEXT_SECONDARY
from ..shell import _nav_html, _page_shell


def _esc(value: object) -> str:
    return _html.escape(str(value), quote=True)


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

    engine_df = engine_df if engine_df is not None and not engine_df.empty else pd.DataFrame()
    catalog = catalog if catalog is not None and not catalog.empty else pd.DataFrame()
    openings_data = openings_data or {}

    panel3 = _build_panel3_figure(engine_df)
    panel3.update_layout(title=None, height=320, margin=dict(l=40, r=20, t=12, b=40), yaxis_title="Win Rate")
    panel3.update_yaxes(title="Win Rate")
    panel3_annotations = getattr(panel3.layout, "annotations", ()) or ()
    panel3.layout.annotations = tuple(
      ann for ann in panel3_annotations if str(getattr(ann, "text", "")).strip() != "50 %"
    )
    panel3_html = panel3.to_html(full_html=False, include_plotlyjs="cdn", config={"scrollZoom": False, "displayModeBar": False})

    family_catalog: dict[str, pd.DataFrame] = {}
    if not catalog.empty and "eco" in catalog.columns:
        catalog_groups = catalog["eco"].astype(str).str[0]
        grouped_catalog = catalog.assign(eco_group=catalog_groups).groupby("eco_group")
        for group, grp in grouped_catalog:
            family_catalog[str(group)] = grp.copy()

    summary = []
    for group in sorted(ECO_COLORS):
        family_actuals = actuals[actuals["eco_group"] == group].copy()
        family_mean_by_eco = family_actuals.groupby("eco")["actual"].mean() if not family_actuals.empty else pd.Series(dtype=float)
        family_catalog_rows = family_catalog.get(group, pd.DataFrame())
        family_openings = int(family_catalog_rows["eco"].nunique()) if not family_catalog_rows.empty else int(family_actuals["eco"].nunique())
        avg_wr = float(family_mean_by_eco.mean()) if not family_mean_by_eco.empty else None
        min_wr = float(family_mean_by_eco.min()) if not family_mean_by_eco.empty else None
        max_wr = float(family_mean_by_eco.max()) if not family_mean_by_eco.empty else None
        tier_counts = {1: 0, 2: 0, 3: 0}
        if not family_catalog_rows.empty and "model_tier" in family_catalog_rows.columns:
            tiers = pd.to_numeric(family_catalog_rows["model_tier"], errors="coerce")
            for tier in (1, 2, 3):
                tier_counts[tier] = int((tiers == tier).sum())
        trend_counts = {"rising": 0, "stable": 0, "falling": 0}
        for eco, opening in openings_data.items():
            if str(eco).startswith(group):
                direction = str(opening.get("trend_direction", "stable")).lower()
                if direction in trend_counts:
                    trend_counts[direction] += 1
        top_eco = None
        top_name = None
        top_delta = None
        if not engine_df.empty and "delta" in engine_df.columns and "eco" in engine_df.columns:
            family_engine = engine_df[engine_df["eco"].astype(str).str.startswith(group)].copy().dropna(subset=["delta"])
            if not family_engine.empty:
                top_pos = int(family_engine["delta"].abs().to_numpy().argmax())
                top_row = family_engine.iloc[top_pos]
                top_eco = str(top_row["eco"])
                top_delta_value = pd.to_numeric(top_row["delta"], errors="coerce")
                top_delta = float(top_delta_value) if pd.notna(top_delta_value) else None
                if not catalog.empty and {"eco", "name"}.issubset(catalog.columns):
                    cat_row = catalog[catalog["eco"].astype(str) == top_eco]
                    if not cat_row.empty:
                        top_name = str(cat_row["name"].iloc[0])
                if top_name is None:
                    top_name = top_eco
        summary.append(
            {
                "group": group,
                "n_ecos": family_openings,
                "avg_wr": avg_wr,
                "min_wr": min_wr,
                "max_wr": max_wr,
                "tier_counts": tier_counts,
                "trend_counts": trend_counts,
                "top_eco": top_eco,
                "top_name": top_name,
                "top_delta": top_delta,
            }
        )

    total_ecos = sum(item["n_ecos"] for item in summary)
    weighted_mean = sum((item["avg_wr"] or 0.0) * item["n_ecos"] for item in summary) / total_ecos if total_ecos > 0 else None
    total_rising = sum(item["trend_counts"]["rising"] for item in summary)

    def _fmt_pct(value: float | None) -> str:
        return f"{value * 100:.2f}%" if value is not None else "—"

    def _fmt_delta(value: float | None) -> str:
        if value is None:
            return "—"
        color = "#7BE495" if value > 0.005 else "#F28DA6" if value < -0.005 else TEXT_SECONDARY
        sign = "+" if value >= 0 else ""
        weight = "700" if value > 0.005 else "600" if value < -0.005 else "500"
        return f'<span style="color:{color};font-weight:{weight}">{sign}{value * 100:.2f} pp</span>'

    def _tier_pills(counts: dict[int, int]) -> str:
        return (
            f'<span class="tier-pill tier-pill-1">T1 {counts.get(1, 0)}</span> '
            f'<span class="tier-pill tier-pill-2">T2 {counts.get(2, 0)}</span> '
            f'<span class="tier-pill tier-pill-3">T3 {counts.get(3, 0)}</span>'
        )

    def _trend_pills(counts: dict[str, int]) -> str:
        parts = []
        if counts.get("rising", 0):
            parts.append(f'<span class="trend-pill trend-pill-rise" title="{counts["rising"]} rising openings">↑ {counts["rising"]}</span>')
        if counts.get("stable", 0):
            parts.append(f'<span class="trend-pill trend-pill-flat" title="{counts["stable"]} flat openings">→ {counts["stable"]}</span>')
        if counts.get("falling", 0):
            parts.append(f'<span class="trend-pill trend-pill-fall" title="{counts["falling"]} falling openings">↓ {counts["falling"]}</span>')
        return " ".join(parts) if parts else "—"

    rows_html = ""
    for item in summary:
        color = ECO_COLORS.get(item["group"], TEXT_PRIMARY)
        outlier_cell = "—"
        if item["top_eco"]:
            top_eco = str(item["top_eco"])
            top_name = str(item["top_name"] if item["top_name"] else item["top_eco"])
            outlier_cell = (
                f'<a href="opening.html?eco={quote(top_eco)}" class="family-outlier-link" style="--link-color:{color}">{_esc(top_eco)}</a>'
                f'<div class="family-outlier-name" title="{_esc(top_name)}">{_esc(top_name)}</div>'
                f'<div class="family-outlier-delta">{_fmt_delta(item["top_delta"])} </div>'
            )
        rows_html += (
            '<tr>'
            f'<td data-label="Family"><span class="family-chip" style="--chip-color:{color}">{_esc(item["group"])}</span></td>'
            f'<td data-label="Openings" style="text-align:center">{item["n_ecos"]}</td>'
            f'<td data-label="Tier split" style="text-align:center">{_tier_pills(item["tier_counts"])}</td>'
            f'<td data-label="Avg win rate" style="text-align:right">{_fmt_pct(item["avg_wr"])}</td>'
            f'<td data-label="Range" style="text-align:right;color:{TEXT_SECONDARY};font-size:0.82rem">{_fmt_pct(item["min_wr"])} \u2013 {_fmt_pct(item["max_wr"])}</td>'
            f'<td data-label="Trends" style="text-align:center">{_trend_pills(item["trend_counts"])}</td>'
            f'<td data-label="Top outlier">{outlier_cell}</td>'
            '</tr>'
        )

    fam_css = """<style>
.families-shell { max-width: 1240px; margin: 0 auto; padding: 3rem 2rem 4rem; }
.families-hero { display: grid; grid-template-columns: 1.35fr 1fr 1fr; gap: 1.25rem; margin-bottom: 1.5rem; }
.engine-box {
  background: var(--surface-raised);
  border: 1px solid rgba(255,255,255,0.10);
  border-radius: 12px;
  padding: 1rem 1.1rem;
}
.families-title { margin: 0 0 0.45rem; font-size: 1.8rem; letter-spacing: -0.02em; }
.families-subtitle { margin: 0; color: var(--text-faint); font-size: 0.75rem; line-height: 1.55; max-width: 36rem; }
.metric-label { margin: 0 0 0.3rem; font-size: 0.65rem; color: var(--text-faint); text-transform: uppercase; letter-spacing: 0.08em; }
.metric-value { margin: 0; font-size: 2rem; font-weight: 700; line-height: 1; color: var(--text-primary); }
.metric-note { margin: 0.55rem 0 0; color: var(--text-secondary); font-size: 0.84rem; line-height: 1.5; }
.families-chart { margin-bottom: 1.35rem; }
.families-table table { margin: 0; }
.families-table thead th {
  font-size: 0.7rem;
  padding-bottom: 8px;
  border-bottom: 1px solid rgba(255,255,255,0.12);
}
.families-table tbody tr:first-child td { padding-top: 0.7rem; }
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
.tier-pill, .trend-pill {
  display: inline-block;
  margin: 0.08rem 0.14rem;
  padding: 0.12rem 0.38rem;
  border-radius: 999px;
  font-size: 0.76rem;
  line-height: 1.2;
  white-space: nowrap;
}
.tier-pill-1 { color: #7CC7FF; background: color-mix(in srgb, #7CC7FF 16%, transparent); }
.tier-pill-2 { color: #B9A5FF; background: color-mix(in srgb, #B9A5FF 16%, transparent); }
.tier-pill-3 { color: __TEXT_SECONDARY__; background: color-mix(in srgb, __TEXT_SECONDARY__ 14%, transparent); }
.trend-pill-rise { color: #7BE495; background: color-mix(in srgb, #7BE495 14%, transparent); }
.trend-pill-flat { color: __TEXT_SECONDARY__; background: color-mix(in srgb, __TEXT_SECONDARY__ 14%, transparent); }
.trend-pill-fall { color: #F28DA6; background: color-mix(in srgb, #F28DA6 14%, transparent); }
.family-outlier-link { color: var(--link-color); text-decoration: none; font-weight: 700; }
.family-outlier-link:hover { text-decoration: underline; }
.family-outlier-name {
  color: var(--text-secondary);
  font-size: 0.78rem;
  line-height: 1.4;
  max-width: 15rem;
  overflow: hidden;
  white-space: nowrap;
  text-overflow: ellipsis;
}
.family-outlier-delta { margin-top: 0.15rem; }
@media (max-width: 1100px) {
  .families-shell { padding: 2rem 1.25rem 3rem; }
  .families-hero { grid-template-columns: 1fr; }
}
@media (max-width: 720px) {
  .tier-pill, .trend-pill { display: inline-block; margin: 0.12rem 0.12rem 0 0; }
  .families-table table, .families-table thead, .families-table tbody, .families-table th, .families-table td, .families-table tr { display: block; }
  .families-table thead { position: absolute; left: -9999px; top: -9999px; }
  .families-table tr { border-bottom: 1px solid rgba(255,255,255,0.08); padding: 0.75rem 0; }
  .families-table td { border: 0; padding: 0.35rem 0; text-align: left !important; }
  .families-table td::before { content: attr(data-label); display: block; font-size: 0.65rem; color: __TEXT_SECONDARY__; text-transform: uppercase; letter-spacing: 0.07em; margin-bottom: 0.2rem; }
}
@media (max-width: 768px) {
  .families-shell { padding-top: 1.5rem; }
  .families-title { font-size: clamp(1.2rem, 3vw, 1.6rem); }
}
</style>""".replace("__TEXT_SECONDARY__", TEXT_SECONDARY)

    mean_text = f"{weighted_mean:.3f}" if weighted_mean is not None else "—"
    body = f"""
<section class="families-shell">
  <section class="families-hero">
    <div class="engine-box">
      <h1 class="families-title">ECO Families</h1>
      <p class="families-subtitle">Family-level performance, tier mix, trend direction, and engine-human outliers across the tracked opening set.</p>
    </div>
    <div class="engine-box">
      <p class="metric-label">Tracked Openings</p>
      <p class="metric-value">{total_ecos}</p>
      <p class="metric-label" style="margin-top:0.9rem;">Weighted Avg Win Rate</p>
      <p class="metric-value">{mean_text}</p>
      <p class="metric-note">Average across families, weighted by the number of openings in each family.</p>
    </div>
    <div class="engine-box">
      <p class="metric-label">Rising Openings</p>
      <p class="metric-value" style="color:#7BE495">{total_rising}</p>
      <p class="metric-note">Openings with positive trend direction in the serialized trend signals.</p>
    </div>
  </section>

  <div class="engine-box families-chart">
    {panel3_html}
  </div>

  <div class="engine-box families-table">
    <table class="data-table" style="margin:0;">
      <thead>
        <tr>
          <th>Family</th>
          <th style="text-align:center">Openings</th>
          <th style="text-align:center">Tier split</th>
          <th style="text-align:right">Avg win rate</th>
          <th style="text-align:right">Range</th>
          <th style="text-align:center">Trends</th>
          <th>Top outlier</th>
        </tr>
      </thead>
      <tbody>{rows_html}</tbody>
    </table>
  </div>
</section>
"""
    return _page_shell("Families", _nav_html("families.html"), body, head_extras=fam_css)


def render_families_page(
    forecasts: pd.DataFrame,
    engine_df: pd.DataFrame | None = None,
    catalog: pd.DataFrame | None = None,
    openings_data: dict | None = None,
) -> str:
    return render_families(forecasts, engine_df=engine_df, catalog=catalog, openings_data=openings_data)