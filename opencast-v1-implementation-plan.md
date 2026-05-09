# OpenCast v1.0.0 Implementation Plan: Forecasting Evaluation, Move-Level Analytics, Engine Integration, and Interactive Opening Board

## Overview

This document turns the roadmap for OpenCast into a concrete implementation plan focused on four tracks: forecasting robustness, product/UX, engine integration, and an interactive opening board feature that makes per-opening pages feel like a real chess product.

The scope assumes the current stack as described in the existing OpenCast roadmap and architecture notes: Python backend with a staged pipeline (fetch → ingest → select → timeseries → enginedelta → report → visualize), tiered modeling (Tier 1 ARIMA, Tier 2 Holt-Winters, Tier 3 descriptive), and a modular static dashboard driven by CSV/JSON outputs, with per-opening pages served from a single `opening.html` template routed by query parameter `?eco=...`.

## Cross-check of the Existing Plan

### Strengths

- The roadmap correctly prioritizes a model evaluation module (`model_eval.py`) before any exploration of additional forecasting methods, avoiding "model shopping" without ground truth error metrics.
- It keeps model complexity constrained to a small, defensible set: naive, rolling mean, ARIMA (Tier 1), Holt-Winters/ETS (Tier 2), and at most one experimental model.
- It explicitly ties evaluation outputs (`model_eval_summary.csv`) to downstream choices in production `timeseries.py` and to UI signals like forecast confidence badges and dimmed forecast sections.
- It defines clear epics for move-level analytics (`move_stats.py`), better trend visualization based on TrendSignal, engine-informed recommendations, and a Vex integration hook, all of which drive concrete chess or engine value instead of adding charts for their own sake.
- It includes a v1.0.0 hardening track that locks schemas, documents Tier semantics, and strengthens error handling and monitoring, which aligns with a stable, public-facing release.

### Gaps and Risks

- The evaluation module is specified conceptually but lacks explicit API contracts (function signatures, config schema, and integration points in CI vs. local/manual runs).
- The critical path from `model_eval_summary.csv` to actual production changes is described verbally but not wired as a concrete selection mechanism (e.g., a reusable "model registry" or selection function used by `timeseries.py`).
- CI/runtime implications of running rolling-origin backtests across all Tier 1/2 openings are noted qualitatively but not bounded by explicit limits or configuration flags.
- There is no explicit ordering or acceptance criteria for each epic.
- Some UX work (forecast confidence indicators, line-level trend tables) is described at a narrative level but lacks the specific data fields that must be added to existing CSV/JSON outputs.

### Verdict

**Promising but incomplete.** The strategy and epics are sound, but the plan needs explicit interfaces, sequencing, and acceptance criteria to be safely implementable without regression risk.

## Guiding Constraints and Non-Goals

### Data and Modeling Constraints

- Monthly series per opening are short (~30–40 points), so high-parameter or heavily tuned models will overfit unless carefully regularized.
- Tier 1 and Tier 2 definitions are already in place: Tier 1 uses ARIMA plus diagnostic tests and engine delta; Tier 2 uses Holt-Winters/ETS; Tier 3 is descriptive only.
- Forecasting evaluation must be offline and reproducible; it should never run inside the monthly production pipeline by default because of CI time and flakiness concerns.

### Non-Goals for v1.0.0

- Adding many new forecasting models (Prophet, TBATS, N-BEATS, deep TS) is explicitly **out of scope** until the evaluation harness demonstrates a clear need.
- Migrating to a full SPA frontend framework or dynamic backend is out of scope; the plan assumes the existing static-site model with JSON/CSV as the data contract.
- Large changes to the Rust fetcher and the underlying data fetch pipeline remain out of scope.

## Track 0: Pre-implementation Readiness

Before starting new implementation, the following readiness steps are required.

### 0.1 Align with Current Main/Develop State

- Ensure all previously merged phases (catalog expansion, modeling tiers, modular dashboard, single-template opening pages, etc.) from earlier PRs are present on the main development branch.
- Confirm that the dashboard is driven by a single `openingsdata.json` and that per-opening pages are template-driven with query parameters.

### 0.2 Verify Existing Pipeline Invariants

- Confirm the pipeline still runs in the expected order: fetch → ingest → selectopenings → timeseries → enginedelta → report → visualize.
- Confirm Tier 1/2/3 behavior:
  - Tier 1 openings produce ARIMA-based forecasts and engine delta.
  - Tier 2 openings produce Holt-Winters forecasts but no engine delta.
  - Tier 3 openings produce descriptive stats only and no forecasts.
- Run the full update workflow once and verify all artifacts (`opening_ts.csv`, `forecasts.csv`, `enginedelta.csv`, `openingsdata.json`) are generated as documented.

### 0.3 Capture Current Data Volume and CI Time

- Measure the current CI runtime for the full pipeline with the existing set of Tier 1/2 openings.
- Count the number of Tier 1 and Tier 2 openings from `openings_catalog.csv` and record this in a short internal note; this drives evaluation sampling and backtest configuration. (Current catalog has 20 Tier 1 core openings: B20 Sicilian, B12 Caro-Kann, C00 French, B01 Scandinavian, C44 King's Pawn, C50 Italian Game, C60 Ruy Lopez, C20 King's Gambit, D00 London System, D06 Queen's Gambit, D30 Queen's Gambit Declined, D70 Grünfeld, E60 King's Indian, E20 Nimzo-Indian, A10 English Opening, A45 Trompowsky, B06 Modern Defense, A00 Polish Opening, C41 Philidor, B07 Pirc Defense.)

## Track 1: Forecasting Robustness & Evaluation (v0.4.x)

This track makes forecasting defensible by building an offline evaluation module and propagating quality signals into production and the UI.

### 1.1 Implement `src/model_eval.py`

**Goal:** Provide a reproducible offline evaluation framework that compares naive, mean/rolling-mean, ARIMA, Holt-Winters, and at most one experimental model across Tier 1/2 openings.

**Responsibilities:**

- Load the processed monthly opening time series (e.g., `data/processed/opening_ts.csv`) including ECO code, month, and `white_win_rate` fields.
- For each opening in Tier 1 and Tier 2:
  - Extract the time series sorted by month.
  - Require a minimum history length (e.g., 30–36 months) before running evaluation.
- Perform rolling-origin evaluation:
  - Choose evaluation cut points starting at some offset (e.g., from month 24 through T − 3).
  - At each cut: train each candidate model on history up to time t, forecast horizons h ∈ {1, 2, 3} months ahead, record point forecasts and predictive intervals where available.
- Compute metrics per (opening, model, horizon):
  - Mean absolute error (MAE) in percentage points of `white_win_rate`.
  - Optional root mean square error (RMSE).
  - Interval coverage: fraction of realized values within the nominal 95% prediction interval.
- Write a single summary CSV `data/output/model_eval_summary.csv` with columns: `eco, model_name, horizon, mae_pp, rmse_pp, coverage_95, n_samples`.

**Interface:**

```python
# src/model_eval.py
from pathlib import Path
from typing import Sequence


def run_model_eval(
    ts_csv: Path,
    catalog_csv: Path,
    output_csv: Path,
    models: Sequence[str] | None = None,
    min_history_months: int = 30,
    start_offset_months: int = 24,
) -> None:
    """Offline rolling-origin evaluation for Tier 1/2 openings.

    - ts_csv: path to opening_ts.csv (monthly series).
    - catalog_csv: path to openings_catalog.csv for tier filtering.
    - output_csv: path to write model_eval_summary.csv.
    - models: subset of {"naive", "mean", "arima", "holt_winters", "experimental"}.
    """
    ...
```

**Integration:** This module is **not** invoked from `main.py` by default. Add a dedicated CLI entry or Makefile target, invoked manually or via a separate `eval.yml` GitHub Actions workflow that runs less frequently than the monthly update.

### 1.2 Restrict and Define Candidate Models

**Candidate set:**

- Baseline 1: Naive last-value forecast.
- Baseline 2: Mean (or rolling mean) forecast, e.g., mean of last 12 months.
- Tier 1: ARIMA, configured as currently implemented for production.
- Tier 2: Holt-Winters / ETS local level model as currently used.
- Optional: A single additional experimental model, such as a local linear trend state-space model, gated behind an explicit flag.

### 1.3 Define Model Selection Rules

**Selection policy:**

- For Tier 1 openings: if ARIMA's MAE improves on naive by ≥1 percentage point across horizons 1–3, mark ARIMA as selected. Otherwise, fall back to Holt-Winters or naive, tagged as "uncertain forecast" in the UI.
- For Tier 2 openings: if Holt-Winters does not beat naive by ≥0.5 percentage points MAE, use naive/mean instead.

**Implementation:** Add `src/model_selection.py` that reads `model_eval_summary.csv` and writes `data/output/model_choice.json`:

```json
{ "A68": {"tier": 1, "model": "arima"}, "A00": {"tier": 1, "model": "naive"}, ... }
```

### 1.4 Integrate Model Choice into `timeseries.py`

- At startup, load `model_choice.json` if present; fall back to tier defaults if absent.
- Per opening, run only the selected model, not all candidates.
- Add a `model_name` column to `forecasts.csv` reflecting the chosen model.
- If `model_choice.json` is missing when expected, log loudly rather than silently fallback.

### 1.5 Calibrate Forecast Intervals and Confidence Labels

- Using `model_eval_summary.csv`, compute empirical coverage of the nominal 95% intervals per model and horizon.
- Determine a scaling factor per model if actual coverage is far from 95%.
- Persist calibration factors in `data/output/interval_calibration.json`.
- In `run_timeseries`, apply the appropriate factor when computing production forecast intervals.
- Derive a simple confidence label (High / Medium / Low) per opening based on MAE and coverage, and include it in `forecasts.csv` or a derived summary file.

## Track 2: Product & UX Enhancements (v0.5.x)

### 2.1 Implement `src/move_stats.py`

**Goal:** Move-level analytics per opening per month so the dashboard can show "lines driving the trend."

**Output schema for `data/output/move_stats.csv`:**

```text
eco, month, uci, san, games, white_win_rate, share_of_games, delta_share_12m, delta_wr_12m
```

**Interface:**

```python
# src/move_stats.py
from pathlib import Path

def run_move_stats(raw_moves_csv: Path, output_csv: Path) -> None:
    """Compute per-move stats and trends by ECO and month."""
    ...
```

Add a pipeline stage `run_move_stats` in `main.py` after ingest and before visualize. On per-opening pages, add a "Lines driving the trend" section: top 3 moves by combination of volume and win-rate change, as a simple table with columns: Move, Share of Games, Win Rate, 12-month Change.

### 2.2 Enhance Trend Visualization in Charts

- Ensure `TrendClassifier` (or equivalent `trendclassifier.py`) computes direction, slope per month, R², sustained streak length, recent volatility, and confidence (High/Medium/Low).
- On per-opening charts: draw a dashed trend line based on OLS fit over actuals, colored by direction (green=rising, red=falling, grey=stable).
- For openings with low TrendSignal confidence, fade or hide the trend line.
- Include TrendSignal fields in `openingsdata.json` so the frontend renders trend lines without additional backend calls.

### 2.3 Add Forecast Quality Signals to the UI

- Per-opening pages: add a "Forecast confidence" badge (High / Medium / Low) from calibrated coverage and MAE.
- Dim the forecast region when confidence is low.
- Overview page: optional summary count of high-confidence forecasts.

## Track 3: Interactive Opening Board (v0.5.x)

This track makes per-opening pages feel like a real chess product by letting users play through the canonical moves of the opening with a visual board — back, forward, jump-to-start.

### 3.1 Define the Data Model for Opening Lines

**Goal:** Each ECO gets one primary line (and optionally 1–2 secondary lines) at a fixed depth (8–12 plies), stored as a curated, hand-maintained file.

**Why curated, not pipeline-generated:** "What is the textbook main line for A68?" is a different problem from "what is A68's win-rate trend?" Mixing them creates pipeline dependencies where none need to exist. The lines data is stable; the timeseries data changes monthly.

**Artifact:** `data/opening_lines.json`

```json
{
  "B20": {
    "lines": [
      {
        "id": "main",
        "name": "Sicilian Defense main line",
        "starting_fen": "startpos",
        "moves_san": ["e4", "c5"]
      }
    ]
  },
  "C60": {
    "lines": [
      {
        "id": "main",
        "name": "Ruy Lopez",
        "starting_fen": "startpos",
        "moves_san": ["e4", "e5", "Nf3", "Nc6", "Bb5"]
      }
    ]
  }
}
```

Immediately after the catalog reaches a stable size (post Phase A), populate this file for all Tier 1 and Tier 2 openings using standard opening theory. For v0.5.x, seed it for all 20 current Tier 1 openings in the catalog: B20, B12, C00, B01, C44, C50, C60, C20, D00, D06, D30, D70, E60, E20, A10, A45, B06, A00, C41, B07.

**Constraints:**
- One primary line per ECO, max 12 plies for initial implementation.
- No branching or deep trees in v1; this is a "play through the main line" experience, not a full opening explorer.
- Lines are not auto-generated from game frequency data; they are curated for correctness.

### 3.2 Pipeline Integration

In `visualizer.py`, add a step that copies `data/opening_lines.json` into `data/output/dashboard/assets/opening_lines.json` as part of `run_visualizer`. This ensures the asset is always present in the deployed dashboard. No structural pipeline changes needed.

```python
# In run_visualizer(), after generating all HTML/CSS/JS assets:
import shutil
shutil.copy("data/opening_lines.json", "data/output/dashboard/assets/opening_lines.json")
```

### 3.3 Frontend Implementation in `opening.html`

**Dependencies (CDN, no npm build step):**

- [`chess.js`](https://github.com/jhlywa/chess.js) — move legality, position state. Load from CDN.
- [`chessground`](https://github.com/lichess-org/chessground) (by Lichess, fits the data source) or `chessboard.js` — visual board rendering. Load from CDN.

Both have CDN-compatible bundles and zero build toolchain requirements, fitting the existing vanilla-JS static-site model.

**JS logic sketch for `opening.html`:**

```javascript
// After loading openingsdata.json and opening_lines.json:

const eco = new URLSearchParams(window.location.search).get('eco');
const lines = openingLines[eco]?.lines ?? [];
const primaryLine = lines.find(l => l.id === 'main') ?? lines[0];

if (primaryLine) {
  const chess = new Chess(); // starts from initial position
  const moves = primaryLine.moves_san;
  let currentIndex = 0;

  const board = Chessground(document.getElementById('board'), {
    fen: chess.fen(),
    viewOnly: true,
    coordinates: true,
  });

  function goToMove(i) {
    chess.reset();
    for (let j = 0; j < i; j++) chess.move(moves[j]);
    board.set({ fen: chess.fen() });
    currentIndex = i;
    renderMoveList(i);
  }

  document.getElementById('btn-next').onclick = () => {
    if (currentIndex < moves.length) goToMove(currentIndex + 1);
  };
  document.getElementById('btn-prev').onclick = () => {
    if (currentIndex > 0) goToMove(currentIndex - 1);
  };
  document.getElementById('btn-start').onclick = () => goToMove(0);

  // Optional: keyboard support
  document.addEventListener('keydown', e => {
    if (e.key === 'ArrowRight') document.getElementById('btn-next').click();
    if (e.key === 'ArrowLeft') document.getElementById('btn-prev').click();
  });

  // Render move list with active highlight
  function renderMoveList(activeIndex) {
    const list = document.getElementById('move-list');
    list.innerHTML = moves.map((m, i) =>
      `<span class="move ${i < activeIndex ? 'played' : ''} ${i === activeIndex - 1 ? 'active' : ''}">${m}</span>`
    ).join(' ');
  }

  goToMove(0); // initialize to start position
}
```

**Layout in the per-opening page:**

Use the existing split-layout convention. Place the board section above the forecast chart as a natural "what is this opening?" orientation before "what is its trend?":

```
┌─────────────────────────────────────────────────────┐
│  [Opening Name]  [ECO Badge]  [Tier Badge]           │
├───────────────────────────┬─────────────────────────┤
│  Chess board              │  Move list               │
│  (square, responsive)     │  e4 c5 Nf3 ...          │
│                           │  ◀  ▶  ↩               │
├───────────────────────────┴─────────────────────────┤
│  Forecast chart (full width)                         │
├──────────────────────────────────────────────────────┤
│  Engine delta  |  Trend signal  |  LLM narrative     │
└──────────────────────────────────────────────────────┘
```

On mobile, stack vertically: board → move list + controls → forecast chart.

### 3.4 Acceptance Criteria

- [x] `data/opening_lines.json` exists with entries for all 20 current Tier 1 openings.
- [x] `opening_lines.json` is copied to `assets/` by `run_visualizer()` on every build.
- [x] Per-opening page loads the board correctly for a known ECO (e.g., `opening.html?eco=C60`).
- [x] Next/Back/Start controls advance and retreat the position correctly.
- [x] Keyboard arrow keys work (Left/Right).
- [x] Move list highlights the current move.
- [x] If `opening_lines.json` has no entry for a given ECO, the board section is hidden cleanly (no JS error, no empty box).
- [x] Board renders correctly on mobile (min width 280px).
- [x] No new npm build step or external toolchain introduced; CDN-only dependencies.

### 3.5 Future Extensions (not v1.0.0 scope)

- Multiple secondary lines per ECO with a line selector.
- Autoplay with configurable speed.
- Highlighting the last move made.
- Connecting the representative FEN at move 8 to the Vex hook artifact for engine analysis (this is the natural bridge once `vex_hook.csv` is live).

## Track 4: Engine Integration & Chess Value (v0.6.x → v1.0.0)

### 4.1 Implement `src/opening_recommend.py`

**Goal:** Produce engine-informed opening recommendations for specific rating bands.

**Inputs:** `enginedelta.csv`, `opening_ts.csv`, `openings_catalog.csv`.

**Scoring:**

The recommendation score combines engine–human delta with trend slope:

\[\text{score} = \Delta_{\text{engine-human}} + \lambda \cdot \text{trend\_slope}\]

where \(\lambda\) is a small tunable weighting factor.

**Output:** `data/output/top_recommendations_<rating>.json`

```json
[
  {"eco": "A68", "name": "Benoni", "score": 0.12, "delta": 0.08, "trend_slope": 0.04},
  ...
]
```

**UI:** A "Recommendations" section on the overview page listing "Over-performing openings vs engine expectation this year."

### 4.2 Design and Emit a Vex Integration Hook

**Output `data/output/vex_hook.csv`:**

```text
eco, representative_fen, engine_human_delta, trend_class
```

The `representative_fen` is the position at end-of-line from `opening_lines.json` (i.e., the FEN after applying all `moves_san`), computed during `run_visualizer` or a dedicated small script. This ties Track 3 (interactive board) and Track 4 (engine integration) together naturally: the canonical line drives both the board UI and the engine test FEN.

## Track 5: v1.0.0 Hardening

### 5.1 Lock and Document Data Schemas

Document the schema for every artifact in `ARCHITECTURE.md` or a dedicated `SCHEMAS.md`:

| Artifact | Owner | Key Columns |
|---|---|---|
| `model_eval_summary.csv` | `model_eval.py` | `eco, model_name, horizon, mae_pp, rmse_pp, coverage_95, n_samples` |
| `model_choice.json` | `model_selection.py` | `{eco: {tier, model}}` |
| `interval_calibration.json` | `model_selection.py` | `{model_name: {horizon: scale_factor}}` |
| `move_stats.csv` | `move_stats.py` | `eco, month, uci, san, games, white_win_rate, share_of_games, delta_share_12m, delta_wr_12m` |
| `opening_lines.json` | hand-maintained | `{eco: {lines: [{id, name, starting_fen, moves_san}]}}` |
| `top_recommendations_*.json` | `opening_recommend.py` | `eco, name, score, delta, trend_slope` |
| `vex_hook.csv` | `opening_recommend.py` or script | `eco, representative_fen, engine_human_delta, trend_class` |

### 5.2 Improve Error Handling and Monitoring

- In fetch and ingest stages, log and propagate missing-month information clearly.
- In timeseries and enginedelta, wrap per-opening modeling in robust exception handling: log failure with ECO and stage, write sentinel rows or skip gracefully instead of crashing.
- Add CI checks on runtime duration; fail the job if it exceeds a configurable limit.

### 5.3 Documentation: "How to Read OpenCast"

Write a "Reading OpenCast" page that explains:

- What each chart shows and how to interpret trend lines and forecast intervals.
- What engine–human delta represents and how to use the interactive board.
- What Tier 1/2/3 mean, with guarantees and non-guarantees.
- Limitations: small sample sizes, sparse openings, noisy trends in Tier 2/3.

## Implementation Sequencing and Milestones

### Milestone 0: Stabilize Current State

- Complete Track 0 readiness steps.
- Run full pipeline and ensure dashboards and outputs match expectations.

### Milestone 1 (v0.4.x): Forecast Evaluation Baseline

- Implement `model_eval.py` and `model_selection.py`.
- Run evaluations, produce `model_eval_summary.csv`.
- Integrate `model_choice.json` into `timeseries.py`.
- Add interval calibration, minimal UI impact.

### Milestone 2 (v0.5.x): Move Analytics + Interactive Board + Forecast Quality

- Implement `move_stats.py` and integrate with per-opening pages.
- Implement Track 3 (interactive board): create `opening_lines.json`, add CDN dependencies, implement board + next/back controls in `opening.html`.
- Wire TrendSignal-based trend lines into charts.
- Surface forecast confidence badges in the UI.

### Milestone 3 (v0.6.x): Engine Recommendations and Vex Hook

- Implement `opening_recommend.py` and recommendations UI section.
- Generate `vex_hook.csv` using representative FENs from `opening_lines.json`.

### Milestone 4 (v1.0.0): Contracts, Docs, and Hardening

- Lock schemas, add column presence assertions.
- Improve error handling and monitoring.
- Write "Reading OpenCast" and Tier explanation docs.
- Tag v1.0.0 after two or more successful monthly runs with the new system.

## Steps You Must Take Before Implementing

1. **Confirm baseline:** Pull latest main/develop, verify pipeline order and tier behaviour, run a full update workflow for a clean starting point.
2. **Inventory Tier 1/2 openings and CI time:** Record counts (currently 20 Tier 1 openings) and current CI runtime to guide evaluation sampling.
3. **Decide on evaluation frequency:** Choose whether `model_eval.py` runs manually, on demand via `eval.yml`, or on a separate long-running CI workflow.
4. **Lock minimal interfaces now:** Agree on file paths and schemas for `model_eval_summary.csv`, `model_choice.json`, `interval_calibration.json`, `move_stats.csv`, and `opening_lines.json` before coding.
5. **Seed `opening_lines.json`:** Before implementing the board widget, manually author the primary line for all 20 current Tier 1 openings (B20, B12, C00, B01, C44, C50, C60, C20, D00, D06, D30, D70, E60, E20, A10, A45, B06, A00, C41, B07). This is a one-time manual effort and unblocks all subsequent frontend work.
6. **Create tracking issues/PR epics:** For each track and milestone, open an issue or epic in the repo to enforce sequencing.
7. **Defer new model exploration:** Explicitly decide not to add any new forecasting model families until Track 1 has run at least once and produced `model_eval_summary.csv`.
