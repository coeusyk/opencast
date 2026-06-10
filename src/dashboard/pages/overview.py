import html as _html
from urllib.parse import quote

import pandas as pd

from ..charts import _build_panel1_figure, _build_panel2_figure, _build_panel3_figure
from ..data_access import CATALOG_CSV
from ..shell import _nav_html, _page_shell


def _esc(value: object) -> str:
    return _html.escape(str(value), quote=True)


def render_overview(
    forecasts: pd.DataFrame,
    engine_df: pd.DataFrame,
    findings_json: dict | None,
  trend_signals: dict | None = None,
  openings_data: dict | None = None,
) -> str:
    """Render data/output/dashboard/index.html."""
    n_openings = int(engine_df["eco"].nunique()) if not engine_df.empty else 0
    actuals_only = forecasts[forecasts["is_forecast"] == False] if not forecasts.empty else pd.DataFrame()
    fc_only = forecasts[forecasts["is_forecast"] == True] if not forecasts.empty else pd.DataFrame()
    n_months = int(actuals_only["month"].nunique()) if not actuals_only.empty else 0
    high_conf_openings = 0
    if not fc_only.empty and "forecast_quality" in fc_only.columns and "eco" in fc_only.columns:
        eco_quality = fc_only.dropna(subset=["eco"]).groupby("eco", as_index=False)["forecast_quality"].first()
        high_conf_openings = int(eco_quality["forecast_quality"].astype(str).str.lower().eq("high").sum())
    last_updated = (findings_json or {}).get("month", "—")

    panels = (findings_json or {}).get("panels", {})
    fc_insight = panels.get("forecast", {}).get("insight", "")
    ed_insight = panels.get("engine_delta", {}).get("insight", "")
    hm_insight = panels.get("heatmap", {}).get("insight", "")

    max_title_chars = 60

    def _split_insight(text: str, fallback_title: str) -> tuple[str, str]:
        if not text or not str(text).strip():
            return fallback_title, ""

        clean = str(text).strip()
        parts = clean.split(". ", 1)
        title = parts[0].rstrip(".").strip() or fallback_title
        if len(title) > max_title_chars:
            title = fallback_title

        body = parts[1].strip() if len(parts) > 1 else ""
        continuations = (
            "however, ",
            "additionally, ",
            "furthermore, ",
            "moreover, ",
            "conversely, ",
            "nevertheless, ",
            "that said, ",
            "in addition, ",
            "as a result, ",
        )
        body_lc = body.lower()
        for continuation in continuations:
            if body_lc.startswith(continuation):
                body = body[len(continuation):].lstrip()
                body = body[0].upper() + body[1:] if body else body
                break

        return title, body

    fc_title, fc_body = _split_insight(str(fc_insight), "Win Rate Trends")
    ed_title, ed_body = _split_insight(str(ed_insight), "Engine vs Human Gap")
    hm_title, hm_body = _split_insight(str(hm_insight), "ECO Family Patterns")

    catalog_names: dict[str, str] = {}
    try:
      catalog_df = pd.read_csv(CATALOG_CSV)
      if {"eco", "name"}.issubset(catalog_df.columns):
        catalog_names = {
          str(row["eco"]): str(row["name"])
          for _, row in catalog_df[["eco", "name"]].dropna(subset=["eco"]).iterrows()
        }
    except Exception:
      catalog_names = {}

    def _resolve_name(eco: str, fallback: str = "") -> str:
      candidate = str(fallback or "").strip()
      if candidate and candidate != eco:
        return candidate
      return str(catalog_names.get(eco, eco))

    abs_delta_eco = "—"
    abs_delta_name = "—"
    abs_delta_val = 0.0
    abs_delta_human = None
    abs_delta_engine = None
    overperformers = 0
    underperformers = 0

    if not engine_df.empty and "delta" in engine_df.columns and "eco" in engine_df.columns:
      summary_df = engine_df.dropna(subset=["delta", "eco"]).copy()
      overperformers = int((summary_df["delta"] >= 0.05).sum())
      underperformers = int((summary_df["delta"] <= -0.05).sum())
      if not summary_df.empty:
        top_abs = summary_df.assign(abs_delta=summary_df["delta"].abs()).sort_values("abs_delta", ascending=False).iloc[0]
        abs_delta_eco = str(top_abs["eco"])
        abs_delta_name = _resolve_name(abs_delta_eco, str(top_abs.get("opening_name", "")))
        abs_delta_val = float(top_abs["delta"])
        if "human_win_rate_2000" in top_abs.index and pd.notna(top_abs.get("human_win_rate_2000")):
          abs_delta_human = float(top_abs["human_win_rate_2000"])
        if "p_engine" in top_abs.index and pd.notna(top_abs.get("p_engine")):
          abs_delta_engine = float(top_abs["p_engine"])

    steep_eco = "—"
    steep_name = "—"
    steep_fc_delta: float | None = None
    ma3_eco = "—"
    ma3_name = "—"
    ma3_delta: float | None = None
    trend_counts = {"rising": 0, "falling": 0, "stable": 0}

    if openings_data:
      for opening in openings_data.values():
        direction = str(opening.get("trend_direction", "stable")).lower()
        if direction in trend_counts:
          trend_counts[direction] += 1

    if trend_signals:
      for eco, signal in trend_signals.items():
        if not openings_data:
          direction = str(getattr(signal, "direction", "stable") or "stable").lower()
          if direction in trend_counts:
            trend_counts[direction] += 1
      strongest_eco = None
      strongest_signal = None
      for eco, signal in trend_signals.items():
        slope = getattr(signal, "slope_per_month", None)
        if slope is None:
          continue
        if strongest_signal is None or abs(float(slope)) > abs(float(getattr(strongest_signal, "slope_per_month", 0.0))):
          strongest_eco = str(eco)
          strongest_signal = signal
      if strongest_eco and strongest_signal is not None:
        steep_eco = strongest_eco
        steep_fc_delta = float(getattr(strongest_signal, "slope_per_month", 0.0))
        names = forecasts[forecasts["eco"] == steep_eco]["opening_name"]
        steep_name = _resolve_name(steep_eco, str(names.iloc[0]).strip() if not names.empty else "")
    elif not forecasts.empty:
      try:
        from ...report import _full_series_ols

        ols_results = _full_series_ols(forecasts)
        for row in ols_results:
          trend_direction = str(row[1] if len(row) > 1 else "stable").lower()
          if trend_direction in trend_counts:
            trend_counts[trend_direction] += 1
        if ols_results:
          steep = max(ols_results, key=lambda row: abs(float(row[2])))
          steep_eco = str(steep[0])
          steep_fc_delta = float(steep[2])
          names = forecasts[forecasts["eco"] == steep_eco]["opening_name"]
          steep_name = _resolve_name(steep_eco, str(names.iloc[0]).strip() if not names.empty else "")
      except Exception:
        pass

    if not actuals_only.empty and {"eco", "month", "actual"}.issubset(actuals_only.columns):
      ma3_scan = actuals_only[["eco", "month", "actual"]].copy()
      ma3_scan["month"] = pd.to_datetime(ma3_scan["month"], errors="coerce")
      ma3_scan["actual"] = pd.to_numeric(ma3_scan["actual"], errors="coerce")
      ma3_scan = ma3_scan.dropna(subset=["month", "actual"])
      rising_candidates: list[tuple[str, float]] = []
      for eco, grp in ma3_scan.groupby("eco"):
        ordered = grp.sort_values("month")
        ma3 = ordered["actual"].rolling(window=3, min_periods=3).mean()
        valid = ma3.dropna()
        if len(valid) >= 2:
          delta_ma3 = float(valid.iloc[-1] - valid.iloc[-2])
          if delta_ma3 > 0:
            rising_candidates.append((str(eco), delta_ma3))
      if rising_candidates:
        ma3_eco, ma3_delta = max(rising_candidates, key=lambda item: item[1])
        names = forecasts[forecasts["eco"] == ma3_eco]["opening_name"]
        ma3_name = _resolve_name(ma3_eco, str(names.iloc[0]).strip() if not names.empty else "")

    abs_delta_text = f"{abs_delta_val * 100:+.2f} pp vs engine"
    abs_delta_class = "positive" if abs_delta_val > 0.005 else "negative" if abs_delta_val < -0.005 else "neutral"
    abs_delta_extra = (
      f"Engine: {abs_delta_engine * 100:.1f}% → Human: {abs_delta_human * 100:.1f}%"
      if abs_delta_human is not None and abs_delta_engine is not None
      else ""
    )
    steep_delta_text = f"{steep_fc_delta * 100:+.4f} pp/month" if steep_fc_delta is not None else "—"
    steep_delta_class = "positive" if (steep_fc_delta or 0) > 0 else "negative" if (steep_fc_delta or 0) < 0 else "neutral"
    ma3_text = f"{ma3_delta * 100:+.2f} pp (last 3M)" if ma3_delta is not None else "—"

    fig1 = _build_panel1_figure(forecasts, engine_df)
    fig1.update_layout(height=400, margin=dict(l=40, r=20, t=50, b=90))
    _plotly_cfg = {"scrollZoom": False, "displayModeBar": False}
    fig1_html = fig1.to_html(full_html=False, include_plotlyjs="cdn", config=_plotly_cfg)

    fig2 = _build_panel2_figure(engine_df)
    fig2.update_layout(height=400, margin=dict(l=40, r=20, t=50, b=90))
    fig2_html = fig2.to_html(full_html=False, include_plotlyjs=False, config=_plotly_cfg)

    fig3 = _build_panel3_figure(engine_df)
    fig3.update_layout(height=400, margin=dict(l=40, r=20, t=50, b=50))
    fig3_html = fig3.to_html(full_html=False, include_plotlyjs=False, config=_plotly_cfg)

    overview_css = """<style>
:root {
  --color-text:       var(--text-primary);
  --color-text-muted: var(--text-secondary);
  --color-text-faint: var(--text-faint);
  --color-surface:    var(--surface);
  --color-border:     var(--border);
  --color-primary:    #4DA3A6;
}
body { font-family: 'Satoshi', 'Inter', sans-serif !important; }
.page-content { max-width: none !important; padding: 0 !important; }
.hero {
  display: grid;
  grid-template-columns: minmax(0, 1.03fr) minmax(0, 0.97fr);
  gap: 4rem;
  align-items: center;
  min-height: calc(100dvh - 52px);
  height: auto;
  overflow: visible;
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
@media (max-height: 860px) and (min-width: 769px) {
  .hero { gap: 2rem; padding-top: 1.5rem; padding-bottom: 1.5rem; }
  .hero-visual { gap: 0.75rem; }
}
.hero-eyebrow {
  font-size: 0.75rem; letter-spacing: 0.1em; text-transform: uppercase;
  color: var(--color-primary); font-weight: 600; margin: 0 0 1rem;
}
.hero-headline {
  font-family: 'Satoshi', 'Inter', sans-serif;
  font-size: clamp(2.25rem, 4.5vw, 3.5rem);
  max-width: 16ch;
  font-weight: 700; line-height: 1.08; letter-spacing: -0.04em;
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
  font-size: 16px; line-height: 1.75;
  color: var(--color-text-muted); max-width: 44ch; margin: 0 0 2rem;
}
.hero-stats { display: flex; flex-wrap: wrap; gap: 0.5rem; margin: 0 0 2rem; }
.stat-pill {
  font-size: 13px; padding: 0.3rem 0.9rem;
  border: 1px solid rgba(255,255,255,0.1);
  border-radius: 9999px; color: var(--color-text-muted);
  font-variant-numeric: tabular-nums;
}
.signal-row {
  display: flex;
  flex-wrap: wrap;
  gap: 0.45rem;
  margin: -1rem 0 2rem;
}
.signal-row-break {
  width: 100%;
  height: 0;
  flex-basis: 100%;
}
.signal-chip {
  display: inline-flex;
  align-items: center;
  gap: 0.35rem;
  font-size: 12px;
  line-height: 1.2;
  padding: 0.3rem 0.7rem;
  border-radius: 999px;
  border: 1px solid rgba(255,255,255,0.12);
  color: var(--color-text-muted);
  background: rgba(255,255,255,0.03);
}
.signal-chip.rise {
  color: #7BE495;
  border-color: rgba(123,228,149,0.28);
  background: rgba(123,228,149,0.10);
}
.signal-chip.fall {
  color: #F28DA6;
  border-color: rgba(242,141,166,0.28);
  background: rgba(242,141,166,0.10);
}
.signal-chip.flat {
  color: var(--color-text-faint);
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
.hero-visual { display: flex; flex-direction: column; gap: 1rem; width: 100%; align-items: stretch; align-self: center; justify-content: center; }
.proof-card {
  background: var(--color-surface);
  border: 1px solid rgba(255,255,255,0.08);
  border-radius: 12px; padding: 1.25rem 1.5rem;
  width: 100%;
  box-sizing: border-box;
  display:grid;
  grid-template-rows:auto 1fr auto;
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
.analysis-section {
  display: grid;
  grid-template-columns: minmax(0, 0.95fr) minmax(0, 1.05fr);
  gap: clamp(1.5rem, 3vw, 3rem);
  width: min(1200px, calc(100% - 3rem));
  margin: 0 auto;
  padding: 3.5rem 0;
  align-items: center;
}
.analysis-section.reverse { direction: rtl; }
.analysis-section.reverse > * { direction: ltr; }
@media (max-width: 768px) {
  .analysis-section, .analysis-section.reverse {
    grid-template-columns: 1fr;
    direction: ltr;
    width: min(1200px, calc(100% - 2rem));
    padding: 2.5rem 0 0;
  }
  .section-copy { padding-top: 0; }
}
.section-copy { padding-top: 0; }
.section-eyebrow {
  font-size: 0.7rem; text-transform: uppercase; letter-spacing: 0.1em;
  color: var(--color-primary); font-weight: 600; margin: 0 0 0.75rem;
}
.section-title {
  font-size: 22px; font-weight: 700; letter-spacing: -0.03em;
  color: var(--color-text); margin: 0 0 0.75rem; line-height: 1.3;
}
.section-body {
  font-size: 15px; line-height: 1.7;
  color: var(--color-text-muted); max-width: 42ch; margin: 0;
}
.section-chart { min-width: 0; }
.browse-link {
  text-align: right; color: var(--color-text-faint);
  font-size: 0.8rem;
  width: min(1200px, calc(100% - 3rem));
  margin: 0 auto;
  padding: 1.5rem 0 4rem;
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
        safe_eco = _esc(eco)
        safe_name = _esc(name)
        safe_label = _esc(label)
        safe_delta_text = _esc(delta_text)
        safe_extra = _esc(extra)
        href = f"opening.html?eco={quote(str(eco))}" if eco != "—" else ""
        if eco != "—":
            value_html = f'<a class="proof-card-eco-link" href="{href}"><p class="proof-value">{safe_eco}</p></a>'
            detail_html = f'<a class="proof-link" href="{href}"><p class="proof-detail">{safe_name}</p></a>'
        else:
            value_html = f'<p class="proof-value">{safe_eco}</p>'
            detail_html = f'<p class="proof-detail">{safe_name}</p>'
        extra_html = f'<p class="proof-extra">{safe_extra}</p>' if extra else ""
        return (
            '<div class="proof-card">'
            f'<p class="proof-label">{safe_label}</p>'
            f'{value_html}'
            f'{detail_html}'
            f'{extra_html}'
            f'<p class="proof-delta {delta_class}">{safe_delta_text}</p>'
            '</div>'
        )

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
        f'<div class="stat-pill" data-count="{n_openings}" data-suffix=" openings tracked">{n_openings} openings tracked</div>'
        f'<div class="stat-pill" data-count="{n_months}" data-suffix=" months of data">{n_months} months of data</div>'
        f'<div class="stat-pill" data-count="{high_conf_openings}" data-suffix=" high-confidence forecasts">{high_conf_openings} high-confidence forecasts</div>'
        f'<div class="stat-pill">Last updated: {_esc(last_updated)}</div>'
        '</div>'
        '<div class="signal-row">'
        f'<span class="signal-chip rise">↑ {_esc(trend_counts["rising"])} rising</span>'
        f'<span class="signal-chip fall">↓ {_esc(trend_counts["falling"])} falling</span>'
        f'<span class="signal-chip flat">→ {_esc(trend_counts["stable"])} stable</span>'
        '<span class="signal-row-break"></span>'
        f'<span class="signal-chip rise">+5pp outperformance: {_esc(overperformers)}</span>'
        f'<span class="signal-chip fall">-5pp underperformance: {_esc(underperformers)}</span>'
        '</div>'
        '<div class="hero-actions">'
        '<a href="openings.html" class="btn-primary">Explore openings</a>'
        '<a href="families.html" class="btn-secondary">ECO families</a>'
        '</div>'
        '</div>'
        '<div class="hero-visual">'
        + _proof_card("Largest absolute engine delta", abs_delta_eco, abs_delta_name, abs_delta_class, abs_delta_text, abs_delta_extra)
        + _proof_card("Largest absolute forecast slope", steep_eco, steep_name, steep_delta_class, steep_delta_text, "OLS trend slope")
        + _proof_card("Fastest rising by 3-month MA", ma3_eco, ma3_name, "positive", ma3_text, "Latest 3M moving-average acceleration")
        + '</div>'
        '</section>'
    )

    def _section(eyebrow: str, title: str, body_text: str, chart_html: str, reverse: bool = False) -> str:
        cls = "analysis-section reverse" if reverse else "analysis-section"
        return (
            f'<section class="{cls}">'
            '<div class="section-copy">'
            f'<p class="section-eyebrow">{_esc(eyebrow)}</p>'
            f'<h2 class="section-title">{_esc(title or eyebrow)}</h2>'
            f'<p class="section-body">{_esc(body_text)}</p>'
            '</div>'
            f'<div class="section-chart">{chart_html}</div>'
            '</section>'
        )

    fc_body_text = str(fc_body or fc_insight or "Recent forecast signal is limited; monitor upcoming months for clearer direction.")
    ed_body_text = str(ed_body or ed_insight or "Engine and practical outcomes are compared to identify where play diverges from theory.")
    hm_body_text = str(hm_body or hm_insight or "Family-level win-rate aggregates highlight where practical performance clusters.")
    if "50%" not in hm_body_text:
      hm_body_text += " Use 50% as parity baseline: persistent deviations indicate family-level practical tilt."

    body = (
        hero_html
        + _section("Win Rate Forecasts", fc_title, fc_body_text, fig1_html)
        + _section("Engine Delta", ed_title, ed_body_text, fig2_html, reverse=True)
        + _section("ECO Family Win Rates", hm_title, hm_body_text, fig3_html)
        + '<p class="browse-link"><a href="openings.html">→ Browse all openings</a></p>'
    )

    return _page_shell("Overview", _nav_html("index.html"), body, head_extras=overview_css)