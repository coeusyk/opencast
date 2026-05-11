import json

from ..tokens import ACCENT, BODY_FONT, DISPLAY_FONT, ECO_COLORS, GRID_COLOR, PANEL_BG, TEXT_PRIMARY, TEXT_SECONDARY
from ..shell import _nav_html, _page_shell


def render_opening_template() -> str:
    body = f"""
<h1 id="opening-title">Opening Detail</h1>
<p style="margin:-0.25rem 0 0.6rem 0; display:flex; gap:0.45rem; align-items:center; flex-wrap:wrap;">
  <span id="opening-tier-badge"></span>
  <span id="opening-model-badge"></span>
  <span id="opening-forecast-quality-badge"></span>
</p>
<p style="margin:0 0 1rem 0;">
  <a id="back-to-openings" href="openings.html" style="color:{TEXT_SECONDARY}; text-decoration:none; font-size:0.85rem;">&larr; All openings</a>
</p>
<div id="opening-narrative" class="engine-box" style="display:none;margin-bottom:1.5rem;"><h3>Analysis</h3><p></p></div>
<div id="opening-board-section" class="engine-box" style="display:none;margin-bottom:1.5rem;">
  <h3 style="margin:0 0 0.5rem;">Opening Board</h3>
  <p id="opening-line-name" style="margin:0 0 0.85rem;color:{TEXT_SECONDARY};font-size:0.84rem;"></p>
  <div class="opening-board-layout">
    <div class="opening-board-frame">
      <div id="opening-board-ranks" class="board-ranks" aria-hidden="true"></div>
      <div id="opening-board" class="opening-board"></div>
      <div id="opening-board-files" class="board-files" aria-hidden="true"></div>
    </div>
    <div class="opening-line-panel">
      <div id="opening-move-list" class="opening-move-list"></div>
      <div class="opening-board-controls">
        <button id="btn-flip" type="button" class="board-btn" aria-label="Flip board" title="Flip Board"><svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 4v7h-7M3 20v-7h7M3.51 9a9 9 0 0 1 14.85-3.36M20.49 15a9 9 0 0 1-14.85 3.36"/></svg></button>
        <button id="btn-reset" type="button" class="board-btn" aria-label="Reset position" title="Reset"><svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 12a9 9 0 0 1 9-9 9.75 9.75 0 0 1 6.74 2.74L21 8M21 3v5h-5M21 12a9 9 0 0 1-9 9 9.75 9.75 0 0 1-6.74-2.74L3 16M3 21v-5h5"/></svg></button>
        <button id="btn-prev" type="button" class="board-btn" aria-label="Move back" title="Move Back"><svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor"><path d="M8 5v14l11-7z" transform="rotate(180 12 12)"/></svg></button>
        <button id="btn-next" type="button" class="board-btn" aria-label="Move forward" title="Move Forward"><svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor"><path d="M8 5v14l11-7z"/></svg></button>
      </div>
    </div>
  </div>
</div>
<div id="historical-summary-box" class="engine-box" style="display:none;margin-bottom:1.5rem;"></div>
<div id="opening-chart"></div>
<div id="forecast-stats-box" class="engine-box" style="display:none;margin-top:1.1rem;margin-bottom:1.5rem;"></div>
<div id="breaks-box" class="engine-box" style="display:none;margin-bottom:1.5rem;"></div>
<div id="lines-box" class="engine-box" style="display:none;"></div>
<div id="engine-box" class="engine-box" style="display:none;"></div>
<div class="mobile-back-bar" role="navigation"><a href="openings.html" id="mobile-back-link" class="mobile-back-btn">&larr; All openings</a></div>
"""
    tier_css = f"""<style>
  .tier-badge {{display:inline-block;padding:0.15em 0.55em;border-radius:4px;font-size:0.75rem;font-weight:600;letter-spacing:0.04em;}}
  .tier-badge-1 {{background:rgba(74,158,255,0.18);color:#4a9eff;}}
  .tier-badge-2 {{background:rgba(169,117,255,0.18);color:#a975ff;}}
  .tier-badge-3 {{background:rgba(139,139,143,0.2);color:{TEXT_SECONDARY};}}
  .meta-badge {{display:inline-block;padding:0.15em 0.55em;border-radius:4px;font-size:0.75rem;font-weight:500;letter-spacing:0.02em;background:rgba(255,255,255,0.08);color:{TEXT_PRIMARY};}}
  .quality-high {{background:rgba(123,228,149,0.18);color:#7BE495;}}
  .quality-medium {{background:rgba(246,193,119,0.18);color:#F6C177;}}
  .quality-low {{background:rgba(242,141,166,0.18);color:#F28DA6;}}
  .stat-chip {{
    display:flex;
    flex-direction:column;
    align-items:flex-start;
    padding:0.45rem 0.85rem;
    background:rgba(255,255,255,0.04);
    border:1px solid rgba(255,255,255,0.09);
    border-radius:8px;
    min-width:112px;
  }}
  .chip-label {{
    font-size:0.68rem;
    text-transform:uppercase;
    letter-spacing:0.08em;
    color:{TEXT_SECONDARY};
    margin-bottom:0.2rem;
  }}
  .chip-value {{ font-size:0.95rem; font-weight:700; }}
  .historical-grid {{ display:grid; grid-template-columns:repeat(4, minmax(0, 1fr)); gap:0.6rem; }}
  .historical-stat {{ background:rgba(255,255,255,0.04); border-radius:8px; padding:0.65rem 0.9rem; }}
  .historical-label {{ margin:0 0 0.2rem; font-size:0.7rem; text-transform:uppercase; letter-spacing:0.08em; color:{TEXT_SECONDARY}; }}
  .historical-value {{ margin:0; font-size:1rem; font-weight:700; color:{TEXT_PRIMARY}; }}
  .opening-board-layout {{
    display:grid;
    grid-template-columns:minmax(280px, 360px) 1fr;
    gap:1rem;
    align-items:start;
  }}
  .opening-board-frame {{
    display:grid;
    grid-template-columns:1rem minmax(280px, 360px);
    grid-template-rows:minmax(280px, 360px) 1rem;
    column-gap:0.45rem;
    row-gap:0.4rem;
    align-items:stretch;
  }}
  .opening-board {{
    grid-column:2;
    grid-row:1;
    width:100%;
    min-width:280px;
    aspect-ratio:1 / 1;
    border-radius:8px;
    overflow:hidden;
    border:1px solid rgba(255,255,255,0.12);
    opacity:1;
    transition:opacity 0.2s ease;
  }}
  .board-ranks {{
    grid-column:1;
    grid-row:1;
    display:grid;
    grid-template-rows:repeat(8, minmax(0, 1fr));
    align-items:center;
    justify-items:center;
    color:{TEXT_SECONDARY};
    font-size:0.72rem;
    font-weight:600;
    user-select:none;
  }}
  .board-files {{
    grid-column:2;
    grid-row:2;
    display:grid;
    grid-template-columns:repeat(8, minmax(0, 1fr));
    align-items:center;
    justify-items:center;
    color:{TEXT_SECONDARY};
    font-size:0.72rem;
    font-weight:600;
    user-select:none;
    text-transform:lowercase;
  }}
  .board-coord {{ line-height:1; }}
  .opening-line-panel {{ display:flex; flex-direction:column; gap:0.7rem; min-width:0; }}
  .opening-move-list {{
    background:rgba(255,255,255,0.03);
    border:1px solid rgba(255,255,255,0.10);
    border-radius:8px;
    padding:0.65rem 0.75rem;
    min-width:0;
    max-height:280px;
    overflow:auto;
  }}
  .move-row {{ display:grid; grid-template-columns:2.1rem minmax(2.2rem, auto) minmax(2.2rem, auto); column-gap:0.65rem; align-items:center; margin-bottom:0.32rem; font-size:0.82rem; }}
  .move-row:last-child {{ margin-bottom:0; }}
  .move-number {{ color:{TEXT_SECONDARY}; font-size:0.76rem; }}
  .move-token {{ color:{TEXT_SECONDARY}; padding:0.06rem 0.24rem; border-radius:4px; line-height:1.2; }}
  .move-token.played {{ color:{TEXT_PRIMARY}; }}
  .move-token.active {{ background:rgba(87,199,255,0.18); color:{TEXT_PRIMARY}; }}
  .opening-board-controls {{ display:flex; gap:0.5rem; flex-wrap:wrap; }}
  .board-btn {{
    border:1px solid rgba(255,255,255,0.16);
    background:rgba(255,255,255,0.04);
    color:{TEXT_PRIMARY};
    font-family:'Satoshi', 'Inter', sans-serif;
    font-size:0.8rem;
    font-weight:600;
    padding:0.42rem 0.55rem;
    min-width:2.7rem;
    height:2.7rem;
    display:flex;
    align-items:center;
    justify-content:center;
    border-radius:6px;
    cursor:pointer;
    transition:all 0.2s cubic-bezier(0.16, 1, 0.3, 1);
  }}
  .board-btn svg {{ display:block; width:20px; height:20px; }}
  .board-btn:hover:not(:disabled) {{ background:rgba(255,255,255,0.08); }}
  .board-btn:active:not(:disabled) {{ transform:scale(0.92); }}
  .board-btn:disabled {{ opacity:0.4; cursor:not-allowed; }}
  .engine-cards {{ display:grid; grid-template-columns:1fr 1fr; gap:0.75rem; margin-bottom:1rem; }}
  .engine-card {{ background:rgba(255,255,255,0.04); border-radius:8px; padding:0.75rem 1rem; }}
  @media (max-width: 860px) {{
    .opening-board-layout {{ grid-template-columns:1fr; }}
    .opening-board-frame {{ grid-template-columns:1rem minmax(0, 1fr); grid-template-rows:minmax(280px, 420px) 1rem; }}
    .opening-board {{ max-width: min(100%, calc(100vw - 3rem - 48px)); margin-inline: auto; }}
    .board-ranks, .board-files {{ font-size: clamp(0.55rem, 2vw, 0.72rem); }}
    .historical-grid {{ grid-template-columns:repeat(2, minmax(0, 1fr)); }}
    .engine-cards {{ grid-template-columns:1fr; gap:0.6rem; }}
    .opening-move-list {{ max-height:none; overflow-x:auto; overflow-y:visible; }}
  }}
  .mobile-back-bar {{
    display:none;
    position:fixed;
    bottom:0; left:0; right:0;
    background:var(--surface);
    border-top:1px solid var(--border);
    padding:0.75rem 1rem;
    z-index:100;
  }}
  .mobile-back-btn {{
    color:var(--text-primary);
    text-decoration:none;
    font-size:0.9rem;
  }}
  @media (max-width: 768px) {{
    .mobile-back-bar {{ display:block; }}
    body {{ padding-bottom: 3.5rem; }}
  }}
</style>"""
    theme_script = f"""<script>
window.__OPENCAST_THEME__ = {{
  panelBg: {json.dumps(PANEL_BG)},
  gridColor: {json.dumps(GRID_COLOR)},
  textPrimary: {json.dumps(TEXT_PRIMARY)},
  textSecondary: {json.dumps(TEXT_SECONDARY)},
  accent: {json.dumps(ACCENT)},
  ecoColors: {json.dumps(ECO_COLORS)},
  bodyFont: {json.dumps(BODY_FONT)},
  displayFont: {json.dumps(DISPLAY_FONT)}
}};
window.__OPENCAST_FALLBACK_NARRATIVE__ = "No analysis available yet.";
</script>"""
    head_extras = (
        tier_css
        + '\n<link rel="stylesheet" href="assets/chessboard-1.0.0.min.css">'
        + '\n<script src="assets/jquery-3.7.1.min.js"></script>'
        + '\n<script src="assets/chess-0.10.3.min.js"></script>'
        + '\n<script src="assets/chessboard-1.0.0.min.js"></script>'
        + '\n<script src="https://cdn.plot.ly/plotly-2.35.2.min.js"></script>'
        + '\n'
        + theme_script
        + '\n<script defer src="assets/opening.js"></script>'
    )
    return _page_shell("Opening Detail", _nav_html("openings.html"), body, head_extras=head_extras)