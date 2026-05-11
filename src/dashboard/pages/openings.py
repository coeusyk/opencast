import pandas as pd

from ..tokens import ACCENT, ECO_COLORS, TEXT_PRIMARY, TEXT_SECONDARY
from ..shell import _nav_html, _page_shell


def render_openings_table(
    forecasts: pd.DataFrame,
    engine_df: pd.DataFrame,
    catalog: pd.DataFrame,
) -> str:
    """Render data/output/dashboard/openings.html."""
    eco_colors_js = __import__("json").dumps(ECO_COLORS)
    group_checkboxes = "\n      ".join(
        f'<label class="ms-item"><input type="checkbox" class="ms-cb" data-filter="group" value="{g}"> {g}</label>'
        for g in sorted(ECO_COLORS)
    )

    table_html = f"""
<h1 class="page-title">All Openings</h1>

<div id="table-controls" class="table-controls" style="display:flex;flex-wrap:wrap;gap:0.75rem;align-items:center;margin-bottom:1.25rem;">
  <input id="search-box" type="search" placeholder="Search ECO or name..."
    aria-label="Search openings"
    style="flex:1;min-width:200px;max-width:360px;padding:0.4rem 0.75rem;
           background:var(--surface-raised);border:1px solid rgba(255,255,255,0.12);
           border-radius:6px;color:var(--text-primary);font-size:0.9rem;outline:none;
           font-family:'Satoshi','Inter',sans-serif;" />

  <details class="ms-dropdown" id="group-dropdown" role="group" aria-label="Filter by class">
    <summary class="ms-summary" id="group-summary"><span class="ms-label">All classes</span></summary>
    <div class="ms-panel" role="group">
      {group_checkboxes}
    </div>
  </details>

  <details class="ms-dropdown" id="tier-dropdown" role="group" aria-label="Filter by tier">
    <summary class="ms-summary" id="tier-summary"><span class="ms-label">All tiers</span></summary>
    <div class="ms-panel" role="group">
      <label class="ms-item"><input type="checkbox" class="ms-cb" data-filter="tier" value="1"> Tier 1</label>
      <label class="ms-item"><input type="checkbox" class="ms-cb" data-filter="tier" value="2"> Tier 2</label>
      <label class="ms-item"><input type="checkbox" class="ms-cb" data-filter="tier" value="3"> Tier 3</label>
    </div>
  </details>

  <details class="ms-dropdown" id="quality-dropdown" role="group" aria-label="Filter by confidence">
    <summary class="ms-summary" id="quality-summary"><span class="ms-label">All confidence</span></summary>
    <div class="ms-panel" role="group">
      <label class="ms-item"><input type="checkbox" class="ms-cb" data-filter="quality" value="high"> High</label>
      <label class="ms-item"><input type="checkbox" class="ms-cb" data-filter="quality" value="medium"> Medium</label>
      <label class="ms-item"><input type="checkbox" class="ms-cb" data-filter="quality" value="low"> Low</label>
    </div>
  </details>

  <span id="row-count" style="color:{TEXT_SECONDARY};font-size:0.85rem;margin-left:auto;white-space:nowrap;"></span>
</div>

<div style="margin:0 0 1.25rem 0;padding:0.8rem 1rem;border:1px solid rgba(255,255,255,0.10);border-radius:8px;background:rgba(255,255,255,0.02);font-family:'Satoshi','Inter',sans-serif;">
  <div style="font-size:0.82rem;color:{TEXT_SECONDARY};line-height:1.6;">
    <strong style="color:{TEXT_PRIMARY};">Tier 1</strong>: at least 1,000 average monthly games and at least 24 months of data (full forecast + engine comparison).<br>
    <strong style="color:{TEXT_PRIMARY};">Tier 2</strong>: 400–999 average monthly games (trend forecast only).<br>
    <strong style="color:{TEXT_PRIMARY};">Tier 3</strong>: under 400 average monthly games (descriptive stats only).
  </div>
</div>

<div class="table-scroll-outer">
<div class="table-scroll-wrap" style="overflow-x:auto;-webkit-overflow-scrolling:touch;">
<table id="openings-table" class="data-table" style="width:100%;min-width:880px;border-collapse:collapse;">
  <thead>
    <tr>
      <th class="sortable" data-col="eco"      style="cursor:pointer;white-space:nowrap;">ECO <span class="sort-icon"></span></th>
      <th class="sortable" data-col="name"     style="cursor:pointer;white-space:nowrap;">Name <span class="sort-icon"></span></th>
      <th class="sortable" data-col="tier"     style="cursor:pointer;white-space:nowrap;">Tier <span class="sort-icon"></span></th>
      <th class="sortable" data-col="win_rate" style="cursor:pointer;white-space:nowrap;">Win Rate (last) <span class="sort-icon"></span></th>
      <th class="sortable" data-col="has_fc"   style="cursor:pointer;white-space:nowrap;">Forecast <span class="sort-icon"></span></th>
      <th class="sortable" data-col="quality"  style="cursor:pointer;white-space:nowrap;">Confidence <span class="sort-icon"></span></th>
      <th class="sortable" data-col="delta"    style="cursor:pointer;white-space:nowrap;">Engine Delta <span class="sort-icon"></span></th>
      <th>Detail</th>
    </tr>
  </thead>
  <tbody id="openings-tbody"></tbody>
</table>
</div>
</div>
<p id="empty-state" style="display:none;color:{TEXT_SECONDARY};text-align:center;padding:2rem;">
  No openings match the current filters.
</p>

<style>
#openings-table tbody tr:hover {{ background: rgba(255,255,255,0.04); cursor:pointer; }}
#openings-table th {{ user-select:none; }}
.sort-icon {{ font-size:0.75rem; opacity:0.5; }}
.table-scroll-outer {{ position:relative; }}
.table-scroll-outer::after {{
  content:'';
  position:absolute;
  top:0; right:0; bottom:0;
  width:3rem;
  background:linear-gradient(to right, transparent, rgba(11,13,16,0.85));
  pointer-events:none;
  border-radius:0 4px 4px 0;
}}
.tier-badge {{ display:inline-block;padding:0.15em 0.55em;border-radius:4px;font-size:0.75rem;font-weight:600;letter-spacing:0.04em; }}
.tier-badge-1 {{ background:rgba(74,158,255,0.18);color:#4a9eff; }}
.tier-badge-2 {{ background:rgba(169,117,255,0.18);color:#a975ff; }}
.tier-badge-3 {{ background:rgba(139,139,143,0.2);color:{TEXT_SECONDARY}; }}
.quality-badge {{ display:inline-block;padding:0.15em 0.55em;border-radius:4px;font-size:0.72rem;font-weight:600;letter-spacing:0.03em;text-transform:capitalize; }}
.quality-badge-high {{ background:rgba(123,228,149,0.18);color:#7BE495; }}
.quality-badge-medium {{ background:rgba(246,193,119,0.18);color:#F6C177; }}
.quality-badge-low {{ background:rgba(242,141,166,0.18);color:#F28DA6; }}
/* Multi-select dropdowns */
.ms-dropdown {{
  position:relative;
}}
.ms-summary {{
  list-style:none;
  padding:0.35rem 2rem 0.35rem 0.6rem;
  background:var(--surface-raised);
  border:1px solid rgba(255,255,255,0.12);
  border-radius:6px;
  color:var(--text-primary);
  font-size:0.85rem;
  cursor:pointer;
  font-family:'Satoshi','Inter',sans-serif;
  white-space:nowrap;
  user-select:none;
  position:relative;
}}
.ms-summary::-webkit-details-marker {{ display:none; }}
.ms-summary::after {{
  content:"▾";
  position:absolute;
  right:0.55rem;
  top:50%;
  transform:translateY(-50%);
  font-size:0.75rem;
  opacity:0.6;
}}
.ms-dropdown[open] .ms-summary::after {{ content:"▴"; }}
.ms-panel {{
  position:absolute;
  top:calc(100% + 4px);
  left:0;
  min-width:140px;
  background:rgba(18,20,24,0.98);
  border:1px solid rgba(255,255,255,0.14);
  border-radius:8px;
  padding:0.45rem;
  z-index:200;
  display:flex;
  flex-direction:column;
  gap:0.1rem;
}}
.ms-item {{
  display:flex;
  align-items:center;
  gap:0.55rem;
  padding:0.5rem 0.6rem;
  border-radius:5px;
  font-size:0.85rem;
  cursor:pointer;
  color:var(--text-primary);
  white-space:nowrap;
}}
.ms-item:hover {{ background:rgba(255,255,255,0.06); }}
.ms-cb {{
  appearance:none;
  -webkit-appearance:none;
  width:1rem;
  height:1rem;
  border:1.5px solid rgba(255,255,255,0.3);
  border-radius:3px;
  background:transparent;
  cursor:pointer;
  flex-shrink:0;
  position:relative;
}}
.ms-cb:checked {{
  background:{ACCENT};
  border-color:{ACCENT};
}}
.ms-cb:checked::after {{
  content:"✓";
  position:absolute;
  top:50%;
  left:50%;
  transform:translate(-50%,-50%);
  font-size:0.65rem;
  color:#0B0D10;
  font-weight:700;
}}
@media (max-width: 900px) {{
  .table-controls {{
    display: grid !important;
    grid-template-columns: 1fr 1fr;
    gap: 0.6rem;
    align-items: stretch;
  }}
  .table-controls #search-box {{
    grid-column: 1 / -1;
    max-width: none !important;
    width: 100%;
  }}
  .table-controls #row-count {{
    grid-column: 1 / -1;
    margin-left: 0 !important;
  }}
  .ms-summary {{ width: 100%; box-sizing: border-box; }}
  .ms-panel {{ min-width: 100%; }}
}}
@media (max-width: 560px) {{
  .table-controls {{
    grid-template-columns: 1fr;
  }}
}}
</style>

<script>
(async () => {{
  const ECO_COLORS = {eco_colors_js};
  const TEXT_SECONDARY = "{TEXT_SECONDARY}";
  const TEXT_PRIMARY   = "{TEXT_PRIMARY}";
  const ACCENT         = "{ACCENT}";
  const QUALITY_ORDER  = {{ "high": 3, "medium": 2, "low": 1 }};

  let openingsData = {{}};
  try {{
    const resp = await fetch("assets/openings_data.json", {{ cache: "no-store" }});
    if (!resp.ok) throw new Error("HTTP " + resp.status);
    openingsData = await resp.json();
  }} catch (e) {{
    const es = document.getElementById("empty-state");
    es.style.display = "block";
    es.textContent = "Failed to load openings data.";
    return;
  }}
  const allRows = Object.entries(openingsData).map(([eco, d]) => {{
    const actuals = d.actuals || [];
    const lastActual = actuals.length ? actuals[actuals.length - 1].win_rate : null;
    return {{
      eco,
      name: d.name || eco,
      group: (eco[0] || "").toUpperCase(),
      tier: d.model_tier != null ? d.model_tier : 99,
      win_rate: lastActual,
      has_fc: (d.forecast || []).length > 0,
      quality: String(d.forecast_quality || "").toLowerCase(),
      delta: d.delta != null ? d.delta : null,
    }};
  }});
  const total = allRows.length;
  const state = {{ q: "", groups: [], tiers: [], qualities: [], sortCol: "eco", asc: true }};

  function readHash() {{
    const h = window.location.hash.slice(1);
    if (!h) return;
    try {{
      const p = new URLSearchParams(h);
      if (p.has("q")) state.q = p.get("q");
      if (p.has("groups")) state.groups = p.get("groups").split(",").filter(Boolean);
      if (p.has("tiers")) state.tiers = p.get("tiers").split(",").filter(Boolean);
      if (p.has("qualities")) state.qualities = p.get("qualities").split(",").filter(Boolean);
      if (p.has("sort")) state.sortCol = p.get("sort");
      if (p.has("asc")) state.asc = p.get("asc") !== "0";
    }} catch (_) {{}}
  }}
  function writeHash() {{
    const p = new URLSearchParams();
    if (state.q) p.set("q", state.q);
    if (state.groups.length) p.set("groups", state.groups.join(","));
    if (state.tiers.length) p.set("tiers", state.tiers.join(","));
    if (state.qualities.length) p.set("qualities", state.qualities.join(","));
    p.set("sort", state.sortCol);
    p.set("asc", state.asc ? "1" : "0");
    history.replaceState(null, "", "#" + p.toString());
  }}
  readHash();

  /* --- Multi-select dropdown helpers --- */
  function syncCheckboxes(filterKey, values) {{
    document.querySelectorAll(`.ms-cb[data-filter="${{filterKey}}"]`).forEach(cb => {{
      cb.checked = values.includes(cb.value);
    }});
  }}
  function updateSummaryLabel(detailsId, summaryId, defaultLabel, values) {{
    const el = document.querySelector(`#${{detailsId}} .ms-label`);
    if (!el) return;
    el.textContent = values.length === 0 ? defaultLabel : values.join(", ");
  }}
  function initDropdown(detailsId, filterKey, stateKey, defaultLabel) {{
    const details = document.getElementById(detailsId);
    if (!details) return;
    /* Close on Escape */
    details.addEventListener("keydown", e => {{
      if (e.key === "Escape") {{ details.removeAttribute("open"); }}
    }});
    /* Close on outside click */
    document.addEventListener("click", e => {{
      if (!details.contains(e.target)) details.removeAttribute("open");
    }}, {{ capture: true }});
    /* Checkbox change */
    details.querySelectorAll(`.ms-cb`).forEach(cb => {{
      cb.addEventListener("change", () => {{
        const checked = [...details.querySelectorAll(".ms-cb:checked")].map(c => c.value);
        state[stateKey] = checked;
        updateSummaryLabel(detailsId, null, defaultLabel, checked);
        applyFilters();
      }});
    }});
    /* Sync initial state */
    syncCheckboxes(filterKey, state[stateKey]);
    updateSummaryLabel(detailsId, null, defaultLabel, state[stateKey]);
  }}

  const searchBox = document.getElementById("search-box");
  const tbody = document.getElementById("openings-tbody");
  const rowCount = document.getElementById("row-count");
  const emptyState = document.getElementById("empty-state");
  const sortHeaders = document.querySelectorAll(".sortable");
  searchBox.value = state.q;

  initDropdown("group-dropdown", "group", "groups", "All classes");
  initDropdown("tier-dropdown", "tier", "tiers", "All tiers");
  initDropdown("quality-dropdown", "quality", "qualities", "All confidence");

  function applyFilters() {{
    const q = state.q.toLowerCase();
    let visible = allRows.filter((r) => {{
      if (state.groups.length && !state.groups.includes(r.group)) return false;
      if (state.tiers.length && !state.tiers.includes(String(r.tier))) return false;
      if (state.qualities.length && !state.qualities.includes(r.quality)) return false;
      if (q && !r.eco.toLowerCase().includes(q) && !r.name.toLowerCase().includes(q)) return false;
      return true;
    }});
    visible.sort((a, b) => {{
      let av, bv;
      if (state.sortCol === "quality") {{
        av = QUALITY_ORDER[a.quality] || 0;
        bv = QUALITY_ORDER[b.quality] || 0;
      }} else {{
        av = a[state.sortCol];
        bv = b[state.sortCol];
        if (av == null && bv == null) return 0;
        if (av == null) return 1;
        if (bv == null) return -1;
        if (typeof av === "string") av = av.toLowerCase();
        if (typeof bv === "string") bv = bv.toLowerCase();
      }}
      if (av < bv) return state.asc ? -1 : 1;
      if (av > bv) return state.asc ? 1 : -1;
      return 0;
    }});
    writeHash();
    renderRows(visible);
    rowCount.textContent = "Showing " + visible.length + " of " + total;
    emptyState.style.display = visible.length === 0 ? "block" : "none";
    updateSortIcons();
  }}
  function fmtPct(v) {{ return v != null ? (v * 100).toFixed(2) + "%" : "—"; }}
  function fmtDelta(v) {{
    if (v == null) return "—";
    return (v >= 0 ? "+" : "") + (v * 100).toFixed(2) + " pp";
  }}
  function deltaColor(v) {{
    if (v == null) return TEXT_SECONDARY;
    return v > 0.005 ? "#7BE495" : v < -0.005 ? "#F28DA6" : TEXT_SECONDARY;
  }}
  const TIER_TOOLTIP = "T1: >=1000 avg monthly games + >=24 months -> model-selected forecast + engine evaluation\\nT2: 400-999 avg monthly games -> model-selected trend, no engine delta\\nT3: <400 avg monthly games -> descriptive stats only";
  function tierBadge(t) {{
    return '<span class="tier-badge tier-badge-' + t + '" title="' + TIER_TOOLTIP + '">T' + t + '</span>';
  }}
  function qualityBadge(q, tier) {{
    if (!q || tier === 3) return '<span style="color:' + TEXT_SECONDARY + '">—</span>';
    return '<span class="quality-badge quality-badge-' + q + '">' + q + '</span>';
  }}
  function renderRows(rows) {{
    const html = rows.map((r) => {{
      const color = ECO_COLORS[r.group] || TEXT_PRIMARY;
      const backState = window.location.hash.slice(1);
      const href = 'opening.html?eco=' + encodeURIComponent(r.eco) + (backState ? '&back=' + backState : '');
      return '<tr tabindex="0" role="link"' +
        ' onclick="location.href=\\'' + href + '\\'"' +
        ' onkeydown="if(event.key===\\'Enter\\'||event.key===\\' \\'){{event.preventDefault();location.href=\\'' + href + '\\'}}">' +
        '<td style="font-weight:600;color:' + color + '">' + r.eco + '</td>' +
        '<td>' + r.name + '</td>' +
        '<td style="text-align:center;">' + tierBadge(r.tier) + '</td>' +
        '<td style="text-align:right;">' + fmtPct(r.win_rate) + '</td>' +
        '<td style="text-align:center;">' + (r.has_fc ? 'Yes' : '<span style="color:' + TEXT_SECONDARY + '">No</span>') + '</td>' +
        '<td style="text-align:center;">' + qualityBadge(r.quality, r.tier) + '</td>' +
        '<td style="text-align:right;color:' + deltaColor(r.delta) + '">' + fmtDelta(r.delta) + '</td>' +
        '<td style="text-align:center;"><a href="' + href + '" style="color:' + ACCENT + ';text-decoration:none;" onclick="event.stopPropagation()">Details</a></td>' +
        '</tr>';
    }}).join('');
    tbody.innerHTML = html || '';
  }}
  function updateSortIcons() {{
    sortHeaders.forEach((th) => {{
      const icon = th.querySelector('.sort-icon');
      if (th.getAttribute('data-col') === state.sortCol) {{
        icon.textContent = state.asc ? ' ^' : ' v';
        icon.style.opacity = '1';
      }} else {{
        icon.textContent = ' ^v';
        icon.style.opacity = '0.3';
      }}
    }});
  }}
  let debounceTimer;
  searchBox.addEventListener('input', () => {{
    clearTimeout(debounceTimer);
    debounceTimer = setTimeout(() => {{ state.q = searchBox.value.trim(); applyFilters(); }}, 200);
  }});
  sortHeaders.forEach((th) => {{
    th.addEventListener('click', () => {{
      const col = th.getAttribute('data-col');
      if (state.sortCol === col) {{ state.asc = !state.asc; }}
      else {{ state.sortCol = col; state.asc = true; }}
      applyFilters();
    }});
  }});
  applyFilters();
}})();
</script>
"""
    return _page_shell("All Openings", _nav_html("openings.html"), table_html)


def render_openings_page(
    forecasts: pd.DataFrame,
    engine_df: pd.DataFrame,
    catalog: pd.DataFrame,
) -> str:
    return render_openings_table(forecasts, engine_df, catalog)