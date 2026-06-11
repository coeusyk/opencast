"""Engine Signals dashboard page.

Covers:
  #43 — scaffold, nav, summary metrics
  #44 — delta distribution chart + divergence tables
  #45 — move lines table + structural break ScatterChart
"""
import html as _html

from ..charts import (
    _PLOTLY_CFG,
    _build_regime_scatter_figure,
    _flatten_regime_points,
)
from ..shell import _nav_html, _page_shell

_REGIME_MIN_ENGINE_CP = 10
_REGIME_MIN_POINTS = 5

FAMILY_COLORS: dict[str, str] = {
    "A": "#7B9FFF",
    "B": "#4DA3A6",
    "C": "#E6A84A",
    "D": "#E07BA0",
    "E": "#A78BFA",
}

# ---------------------------------------------------------------------------
# Client-side JS — delta chart + divergence tables from openings_data.json.
# Regime scatter is server-rendered Plotly at build time.
# ---------------------------------------------------------------------------
_ENGINE_JS = r"""
const FAM_COLORS = {A:"#7B9FFF",B:"#4DA3A6",C:"#E6A84A",D:"#E07BA0",E:"#A78BFA"};

// ── Bootstrap ───────────────────────────────────────────────────────────────
(async () => {
  let data;
  try {
    const r = await fetch("assets/openings_data.json", {cache:"no-store"});
    if (!r.ok) throw new Error("HTTP " + r.status);
    data = await r.json();
  } catch(e) { return; }

  const withDelta = Object.entries(data)
    .filter(([, d]) => d.delta != null)
    .map(([eco, d]) => ({
      eco, name: d.name || eco,
      delta: d.delta, engine_cp: d.engine_cp,
      forecast_quality: d.forecast_quality,
      model_tier: d.model_tier
    }));

  const tier1 = withDelta.filter(d => d.model_tier === 1);
  buildDeltaChart(tier1);
  buildDivergenceTables(withDelta);
})();

// ── Section 1: Engine Delta Distribution ────────────────────────────────────
function buildDeltaChart(tier1) {
  const section   = document.getElementById("delta-section");
  const container = document.getElementById("delta-chart-rows");
  if (!container) return;
  if (!tier1.length) {
    if (section) section.style.display = "none";
    return;
  }

  // Top 12 positive (human > engine), then top 12 negative (engine > human)
  const pos    = tier1.filter(d => d.delta > 0).sort((a,b) => b.delta - a.delta).slice(0, 12);
  const neg    = tier1.filter(d => d.delta <= 0).sort((a,b) => a.delta - b.delta).slice(0, 12);
  const subset = [...pos, ...neg];
  const maxAbs = Math.max(...subset.map(d => Math.abs(d.delta)));
  const lastPosIdx = pos.length - 1;

  const rows = subset.map((d, i) => {
    const isPos    = d.delta > 0;
    const halfPct  = maxAbs > 0 ? (Math.abs(d.delta) / (2 * maxAbs)) * 50 : 0;
    const barColor = isPos ? "#4DA3A6" : "#D163A7";
    const famColor = FAM_COLORS[d.eco[0]] || "#8b8b8f";
    const sign     = isPos ? "+" : "";
    const valStr   = sign + (d.delta * 100).toFixed(1) + " pp";
    const barLeft  = isPos ? "50%" : (50 - halfPct) + "%";
    const dividerStyle = (i === lastPosIdx && i < subset.length - 1)
      ? ' style="border-bottom:1px solid rgba(255,255,255,0.08)"'
      : "";
    return (
      `<div class="delta-row"${dividerStyle}>` +
        `<span class="delta-eco" style="color:${famColor}">${d.eco}</span>` +
        `<div class="delta-bar-area">` +
          `<div class="delta-zero-line"></div>` +
          `<div class="delta-bar" style="left:${barLeft};width:${halfPct}%;background:${barColor}"></div>` +
        `</div>` +
        `<span class="delta-value" style="color:${barColor}">${valStr}</span>` +
      `</div>`
    );
  });

  container.innerHTML = rows.join("");
}

// ── Section 2: Divergence Tables ────────────────────────────────────────────
function buildDivergenceTables(openings) {
  const section = document.getElementById("tables-section");
  if (!section) return;
  if (!openings.length) { section.style.display = "none"; return; }

  function confChip(quality) {
    if (!quality) return `<span style="color:var(--text-faint)">—</span>`;
    const colors = {high:"#7BE495", medium:"#F6C177", low:"#8b8b8f"};
    const label  = quality === "medium" ? "med" : quality;
    const color  = colors[quality] || "#8b8b8f";
    return `<span style="padding:0.1rem 0.4rem;border-radius:4px;font-size:0.7rem;font-weight:600;background:rgba(255,255,255,0.05);color:${color}">${label}</span>`;
  }

  function makeTable(rows, side) {
    const sorted = [...rows]
      .sort((a, b) => side === "pos" ? b.delta - a.delta : a.delta - b.delta)
      .slice(0, 20);
    const trs = sorted.map(d => {
      const fColor = FAM_COLORS[d.eco[0]] || "#8b8b8f";
      const dColor = d.delta > 0 ? "#7BE495" : "#F28DA6";
      const dStr   = (d.delta > 0 ? "+" : "") + (d.delta * 100).toFixed(1);
      const cp     = d.engine_cp != null ? (d.engine_cp > 0 ? "+" : "") + d.engine_cp : "—";
      const esc = s => String(s).replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/"/g,"&quot;");
      return (
        `<tr onclick="location.href='opening.html?eco=${encodeURIComponent(d.eco)}'" style="cursor:pointer">` +
          `<td><span style="color:${fColor};font-weight:700">${d.eco}</span></td>` +
          `<td class="divergence-name-cell" title="${esc(d.name)}">${esc(d.name)}</td>` +
          `<td style="color:var(--text-secondary);font-variant-numeric:tabular-nums;text-align:right">${cp}</td>` +
          `<td style="color:${dColor};font-weight:600;font-variant-numeric:tabular-nums;text-align:right">${dStr} pp</td>` +
          `<td style="text-align:center">${confChip(d.forecast_quality)}</td>` +
        `</tr>`
      );
    }).join("");
    return (
      `<table class="data-table divergence-table">` +
        `<thead><tr>` +
          `<th style="width:12%">ECO</th>` +
          `<th style="width:38%">OPENING NAME</th>` +
          `<th style="width:16%;text-align:right">ENGINE CP</th>` +
          `<th style="width:18%;text-align:right">\u0394 (PP)</th>` +
          `<th style="width:16%;text-align:center">CONF.</th>` +
        `</tr></thead>` +
        `<tbody>${trs}</tbody>` +
      `</table>`
    );
  }

  const posEl = document.getElementById("table-human-wins");
  const negEl = document.getElementById("table-engine-wins");
  if (posEl) posEl.innerHTML = makeTable(openings, "pos");
  if (negEl) negEl.innerHTML = makeTable(openings, "neg");
}
"""

_ENGINE_CSS = """<style>
.engine-shell { max-width: 1240px; margin: 0 auto; padding: 1.5rem 1.5rem 4rem; }

/* Header */
.engine-header   { margin-bottom: 1.5rem; }
.engine-title    { font-family: var(--font-brand); font-size: 1.8rem; font-weight: 700; letter-spacing: -0.02em; margin: 0 0 0.45rem; }
.engine-subtitle { margin: 0; color: var(--text-secondary); font-size: 0.875rem; line-height: 1.55; max-width: 52rem; }

/* Metrics row */
.engine-metrics {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 1rem;
  margin-bottom: 1.75rem;
}
.metric-tile  { background: var(--surface-raised); border: 1px solid var(--border); border-radius: var(--radius-md); padding: 1rem 1.25rem; }
.metric-label { margin: 0 0 0.35rem; font-size: 0.8125rem; color: var(--text-faint); text-transform: uppercase; letter-spacing: 0.07em; font-family: var(--font-brand); font-weight: 600; }
.metric-value { margin: 0; font-size: 1.75rem; font-weight: 700; line-height: 1; color: var(--text-primary); font-family: var(--font-brand); }
.metric-sub   { margin: 0.35rem 0 0; color: var(--text-faint); font-size: 0.72rem; line-height: 1.5; }

/* Section wrapper */
.engine-section          { margin-bottom: 2.25rem; }
.engine-section-box      { background: var(--surface-raised); border: 1px solid var(--border); border-radius: var(--radius-md); padding: 1.1rem 1.25rem; overflow: clip; }
.engine-section-title    { font-family: var(--font-brand); font-size: 1rem; font-weight: 600; color: var(--text-primary); margin: 0 0 0.25rem; }
.engine-section-subtitle { color: var(--text-secondary); font-size: 0.8rem; line-height: 1.55; margin: 0 0 1rem; max-width: 52rem; }

/* Delta chart */
.delta-legend      { display: flex; gap: 1.25rem; margin-bottom: 0.75rem; align-items: center; flex-wrap: wrap; }
.delta-legend-item { font-size: 0.78rem; color: var(--text-secondary); font-family: var(--font-brand); display: flex; align-items: center; gap: 0.35rem; }
.delta-swatch      { display: inline-block; width: 10px; height: 10px; border-radius: 2px; flex-shrink: 0; }
#delta-chart-rows  { max-height: 560px; overflow-y: auto; padding-right: 0.25rem; scrollbar-gutter: stable; }
.delta-row         { display: flex; align-items: center; height: 22px; gap: 0.5rem; }
.delta-row:hover   { background: rgba(255,255,255,0.02); }
.delta-eco         { width: 44px; font-family: monospace; font-size: 11px; color: var(--text-faint); text-align: right; flex-shrink: 0; }
.delta-bar-area    { flex: 1; position: relative; height: 22px; display: flex; align-items: center; }
.delta-zero-line   { position: absolute; left: 50%; top: 0; bottom: 0; width: 1px; background: rgba(255,255,255,0.15); pointer-events: none; }
.delta-bar         { position: absolute; height: 10px; border-radius: 2px; }
.delta-value       { font-size: 11px; font-weight: 600; white-space: nowrap; min-width: 60px; }

/* Divergence tables — card layout */
.divergence-wrap { display: grid; grid-template-columns: 1fr 1fr; gap: 1.25rem; align-items: stretch; min-width: 0; }
.divergence-card {
  background: var(--surface-raised); border: 1px solid var(--border);
  border-radius: var(--radius-md); display: flex; flex-direction: column;
  min-height: 0; min-width: 0; overflow: hidden;
}
.divergence-card-header {
  display: flex; align-items: center; gap: 0.5rem;
  padding: 0.85rem 1rem 0.6rem; border-bottom: 1px solid var(--border);
}
.divergence-card-title { font-family: var(--font-brand); font-size: 0.875rem; font-weight: 600; color: var(--text-primary); }
.divergence-card-badge {
  margin-left: auto;
  font-size: 0.65rem; font-weight: 600; letter-spacing: 0.05em;
  color: var(--text-secondary);
  background: var(--surface-2);
  border: 1px solid var(--border-strong);
  padding: 0.12rem 0.5rem; border-radius: 999px;
}
.divergence-card-body  { overflow-x: hidden; overflow-y: auto; max-height: 540px; scrollbar-gutter: stable; }
.divergence-table { table-layout: fixed; width: 100%; }
.divergence-table th:nth-child(2),
.divergence-table td.divergence-name-cell {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 0;
  color: var(--text-secondary);
}

/* Regime chart */
#regime-chart-mount {
  background: #0B0D10; border: 1px solid var(--border);
  border-radius: var(--radius-md); min-height: 240px; overflow: clip;
}
#regime-chart-mount .chart-unavailable {
  display: flex; align-items: center; padding: 1rem;
  font-size: 0.78rem; color: var(--text-faint);
}
.chart-unavailable { font-size: 0.75rem; color: var(--text-faint); }

/* Responsive */
@media (max-width: 900px) { .engine-metrics { grid-template-columns: 1fr 1fr; } }
@media (max-width: 600px) { .engine-metrics { grid-template-columns: 1fr; } }
@media (max-width: 768px) {
  .divergence-wrap { grid-template-columns: 1fr; }
  .engine-shell    { padding: 0.75rem 0.75rem 2.5rem; }
}
</style>"""


# ---------------------------------------------------------------------------
# Public renderer — receives openings_data dict (same object written to
# assets/openings_data.json by data_access.py).
# ---------------------------------------------------------------------------

def render_engine(openings_data: dict) -> str:
    """Render data/output/dashboard/engine.html."""

    def _esc(v: object) -> str:
        return _html.escape(str(v), quote=True)

    # ── Server-side metric computation ─────────────────────────────────────
    evaluated_pairs = [
        (eco, d) for eco, d in openings_data.items()
        if d.get("engine_cp") is not None
    ]
    n_evaluated = len(evaluated_pairs)

    delta_pairs = [
        (eco, d) for eco, d in openings_data.items()
        if d.get("delta") is not None
    ]

    best_human = max(delta_pairs, key=lambda x: x[1]["delta"], default=None)
    best_engine = min(delta_pairs, key=lambda x: x[1]["delta"], default=None)

    # Tile 1
    tile1 = (
        f'<div class="metric-tile">'
        f'<p class="metric-label">Openings Evaluated</p>'
        f'<p class="metric-value">{n_evaluated}</p>'
        f'<p class="metric-sub">Engine depth 20 comparisons available.</p>'
        f"</div>"
    )

    # Tile 2 — Largest Human Outperformance
    if best_human:
        eco2, d2 = best_human
        name2 = _esc(d2.get("name") or eco2)
        val2 = f"+{d2['delta'] * 100:.2f} pp"
        tile2 = (
            f'<div class="metric-tile">'
            f'<p class="metric-label">Largest Human Outperformance</p>'
            f'<p class="metric-value" style="color:#7BE495">{_esc(val2)}</p>'
            f'<p class="metric-sub">{_esc(eco2)} — {name2}</p>'
            f"</div>"
        )
    else:
        tile2 = (
            f'<div class="metric-tile">'
            f'<p class="metric-label">Largest Human Outperformance</p>'
            f'<p class="metric-value">—</p>'
            f"</div>"
        )

    # Tile 3 — Largest Engine Advantage
    if best_engine:
        eco3, d3 = best_engine
        name3 = _esc(d3.get("name") or eco3)
        val3 = f"{d3['delta'] * 100:.2f} pp"
        tile3 = (
            f'<div class="metric-tile">'
            f'<p class="metric-label">Largest Engine Advantage</p>'
            f'<p class="metric-value" style="color:#F28DA6">{_esc(val3)}</p>'
            f'<p class="metric-sub">{_esc(eco3)} — {name3}</p>'
            f"</div>"
        )
    else:
        tile3 = (
            f'<div class="metric-tile">'
            f'<p class="metric-label">Largest Engine Advantage</p>'
            f'<p class="metric-value">—</p>'
            f"</div>"
        )

    subtitle = (
        f"Stockfish evaluation vs. human performance across {n_evaluated} openings. "
        f"Identifies where engine theory and human play diverge — useful for "
        f"opening book construction and engine tuning."
    )

    regime_points = _flatten_regime_points(
        openings_data, min_engine_cp=_REGIME_MIN_ENGINE_CP,
    )
    show_regime_chart = len(regime_points) >= _REGIME_MIN_POINTS
    if show_regime_chart:
        regime_fig = _build_regime_scatter_figure(
            openings_data,
            min_engine_cp=_REGIME_MIN_ENGINE_CP,
            min_points=_REGIME_MIN_POINTS,
        )
        regime_mount_html = regime_fig.to_html(
            full_html=False,
            include_plotlyjs="cdn",
            config=_PLOTLY_CFG,
            div_id="regime-chart-plot",
        )
    else:
        regime_mount_html = (
            '<p style="padding:1.5rem 0;text-align:center;color:var(--text-faint);'
            'font-size:0.85rem">No significant regime changes detected.</p>'
        )

    body = f"""
<section class="engine-shell">

  <!-- Header -->
  <section class="engine-header">
    <h1 class="engine-title">Engine Signals</h1>
    <p class="engine-subtitle">{_esc(subtitle)}</p>
  </section>

  <!-- Summary metrics -->
  <section class="engine-metrics">
    {tile1}
    {tile2}
    {tile3}
  </section>

  <!-- Section 1: Delta Distribution -->
  <section class="engine-section" id="delta-section">
    <h2 class="engine-section-title">Human vs Engine Win Probability</h2>
    <p class="engine-section-subtitle">
      Delta = human win rate − Stockfish win probability (depth 20).
      Positive = humans outperform engine prediction.
      Top 12 per side by absolute delta. Tier-1 openings only.
    </p>
    <div class="engine-section-box">
      <div class="delta-legend">
        <span class="delta-legend-item">
          <span class="delta-swatch" style="background:#4DA3A6"></span>Human outperforms engine
        </span>
        <span class="delta-legend-item">
          <span class="delta-swatch" style="background:#D163A7"></span>Engine outperforms human
        </span>
      </div>
      <div id="delta-chart-rows" class="scroll-subtle">
        <p style="color:var(--text-faint);font-size:0.8rem">Loading…</p>
      </div>
    </div>
  </section>

  <!-- Section 2: Divergence Tables -->
  <section class="engine-section" id="tables-section">
    <h2 class="engine-section-title">Greatest Engine–Human Gaps</h2>
    <p class="engine-section-subtitle">
      Openings where engine evaluation most diverges from human outcomes.
      These are the positions most worth studying for engine book depth.
    </p>
    <div class="divergence-wrap">
      <div class="divergence-card">
        <div class="divergence-card-header">
          <span class="divergence-card-title">Human Outperforms Engine</span>
          <span class="divergence-card-badge">Top 20</span>
        </div>
        <div id="table-human-wins" class="divergence-card-body scroll-subtle">
          <p style="padding:1rem;color:var(--text-faint);font-size:0.8rem">Loading…</p>
        </div>
      </div>
      <div class="divergence-card">
        <div class="divergence-card-header">
          <span class="divergence-card-title">Engine Outperforms Human</span>
          <span class="divergence-card-badge">Top 20</span>
        </div>
        <div id="table-engine-wins" class="divergence-card-body scroll-subtle">
          <p style="padding:1rem;color:var(--text-faint);font-size:0.8rem">Loading…</p>
        </div>
      </div>
    </div>
  </section>

  <!-- Section 3: Structural Break Events -->
  <section class="engine-section" id="regime-section">
    <h2 class="engine-section-title">Structural Break Events</h2>
    <p class="engine-section-subtitle">
      Months where a win-rate regime change was detected.
      These often mark when a new engine line entered widespread human play.
      Dot size scaled by absolute engine evaluation (centipawns).
    </p>
    <div id="regime-chart-mount">
      {regime_mount_html}
    </div>
  </section>

</section>
"""

    return _page_shell(
        "Engine",
        _nav_html("engine.html"),
        body,
        head_extras=_ENGINE_CSS,
        body_extras=f'<script>{_ENGINE_JS}</script>',
    )
