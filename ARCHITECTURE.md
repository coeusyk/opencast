# OpenCast — Architecture

## Project Goal

Forecast chess opening win rate trajectories using model-selected time-series forecasting,
and quantify the gap between engine-theoretical win probability and actual human
performance across rating brackets. Two differentiators over existing Lichess
analytics projects:

1. **Per-opening model selection** on monthly win rate time series (ARIMA/Holt-Winters/mean/naive)
2. **Engine-human delta** — Stockfish centipawn eval vs actual human win rate

**v0.4.0 release note (Track 1):** model selection artifacts added (`model_choice.json`, `interval_calibration.json`); current selection run chose 249 Holt-Winters and 29 mean models across 278 forecasted ECOs.

---

## Model Tier Classification

| Tier | Condition | Model |
|---|---|---|
| 1 | `avg_monthly_games ≥ 1000` AND `months_with_data ≥ 24` | Model-selected forecast (ARIMA / Holt-Winters / mean / naive) |
| 2 | `avg_monthly_games ≥ 500` AND `is_long_tail` | Model-selected trend (Holt-Winters / mean) |
| 3 | `avg_monthly_games ≥ 100` AND `is_long_tail` | Descriptive stats only |

---

## Data Flow

```
openings_catalog.csv  (498 ECO codes, tier flags)
        │
        ▼
  [scripts/temp_bootstrap_openings.py]
    batch selection (--eco-offset / --limit)
    per-ECO fetch dispatch + early-stop pruning
    tracks: bootstrap_fetch_complete, bootstrap_fetch_status
        │
        ▼
  [Rust Fetcher  fetcher v0.2.x]
    queries explorer.lichess.ovh month-by-month
    early-stop: if below-min-game ratio exceeds --max-skipped-ratio
    on early-stop: deletes partial raw + tmp files immediately
        │
        ▼
  data/raw/{ECO}.json          ← one consolidated file per ECO
    { "months": [...], "_meta": { "skipped_months": [...] } }
        │
        ▼
  [src/ingest.py]  ── normalized DataFrame ──────────────▶  data/processed/openings_ts.csv
        │
      ├──▶ [src/move_stats.py]
      │       per-move monthly line analytics
      │       → data/output/move_stats.csv
      │
        ├──▶ [src/select_openings.py]
        │       tier classification → openings_catalog.csv (updated in-place)
        │       scripts/compute_selection_flags.py → data/selection_flags.csv
        │
        ├──▶ [src/timeseries.py]
      │       model-selected forecasting + Chow break detection
        │       → data/output/forecasts.csv
        │
        ├──▶ [src/engine_delta.py]
        │       Stockfish (UCI, depth 20) ◀── FEN after move 8 of each Tier-1 opening
        │       centipawn → win probability → delta
        │       → data/output/engine_delta.csv
        │
        ├──▶ [src/report.py]
        │       Groq API (llama-3.1-8b-instant) or templated fallback
        │       → findings/findings.md
        │       → findings/findings.json
        │       → findings/narratives.json  (per-ECO narrative, merged incrementally)
        │
        └──▶ [src/visualizer.py] (compatibility facade)
          delegates to src/dashboard/* package
          multi-page static site → data/output/dashboard/
```

**Key API constraint:** Lichess Explorer supports `since` and `until` as `YYYY-MM`
query params — monthly snapshots without touching multi-GB PGN dumps.

---

## File Structure

```
opencast/
│
├── fetcher/                   ← Rust binary (v0.2.x)
│   ├── src/
│   │   ├── main.rs            ← CLI entry: ECO/month loop, early-stop logic
│   │   ├── client.rs          ← reqwest HTTP logic, MonthFetchOutcome enum
│   │   └── models.rs          ← serde structs for API response
│   └── Cargo.toml             ← version 0.2.0
│
├── scripts/
│   ├── build_catalog.py           ← build/refresh full ECO catalog
│   ├── compute_selection_flags.py ← tier flags + pruning → selection_flags.csv
│   ├── temp_bootstrap_openings.py ← batch bootstrap fetch (--eco-offset / --limit)
│   └── migrate_raw.py             ← legacy raw format migration helper
│
├── data/
│   ├── raw/                   ← one consolidated JSON per ECO (gitignored)
│   │                             { months: [...], _meta: { skipped_months: [...] } }
│   ├── processed/
│   │   └── openings_ts.csv    ← (month, eco, opening_name, rating, white, draws, black, total)
│   ├── openings_catalog.csv   ← 498 ECO codes, tier flags, bootstrap tracking fields
│   ├── selection_flags.csv    ← per-ECO coverage/tier diagnostics
│   └── output/
│       ├── forecasts.csv      ← ARIMA / HW forecasts with confidence intervals
│       ├── move_stats.csv     ← per-move monthly share/win-rate trend metrics
│       ├── engine_delta.csv   ← centipawn vs human win rate delta per opening
│       └── dashboard/         ← multi-page static site (served as GitHub Pages root)
│           ├── index.html     ← overview: headline insights + 3 panels
│           ├── openings.html  ← sortable/filterable table of all openings
│           ├── families.html  ← ECO family summary (A–E)
│           ├── opening.html   ← single per-opening template (use ?eco=B20)
│           └── assets/
│               ├── shared.css ← design tokens, nav, table, widget styles
│               └── nav.js     ← active-link highlight script
│
├── findings/
│   ├── findings.md            ← narrative findings report (auto-generated)
│   └── findings.json          ← structured findings payload (Groq or templated)
│   └── narratives.json        ← per-ECO narrative text (merged incrementally)
│
├── src/
│   ├── __init__.py
│   ├── ingest.py              ← consolidated raw JSON → openings_ts.csv
│   ├── move_stats.py          ← per-move monthly analytics → move_stats.csv
│   ├── select_openings.py     ← per-ECO tier classification → openings_catalog.csv
│   ├── timeseries.py          ← model-selected forecasting + break detection
│   ├── engine_delta.py        ← Stockfish eval → delta computation (Tier 1 only)
│   ├── report.py              ← Groq LLM → findings.md + findings.json + narratives.json
│   ├── visualizer.py          ← public compatibility facade for dashboard generation
│   ├── dashboard/
│   │   ├── __init__.py
│   │   ├── builder.py         ← orchestration entrypoint (run_visualizer)
│   │   ├── data_access.py     ← dashboard paths + loaders + serialization
│   │   ├── charts.py          ← Plotly panel builders
│   │   ├── tokens.py          ← shared dashboard design tokens
│   │   ├── shell.py           ← shared HTML shell + nav
│   │   └── pages/
│   │       ├── __init__.py
│   │       ├── overview.py    ← index.html renderer
│   │       ├── openings.py    ← openings.html renderer
│   │       ├── families.py    ← families.html renderer
│   │       └── opening_template.py ← opening.html renderer
│   └── assets/
│       ├── shared.css         ← design tokens + component styles (source)
│       ├── nav.js             ← active-nav script (source)
│       └── opening.js         ← per-opening client logic (source)
│
├── openings.json              ← seed opening definitions (legacy bootstrap input)
├── main.py                    ← orchestrator: runs all pipeline stages in order
├── requirements.txt
├── ARCHITECTURE.md            ← this file
└── README.md                  ← project overview + pipeline documentation
```

---

## Module Specifications

### `fetcher/` — Rust binary (v0.2.x)

**Responsibility:** Pull monthly win rate snapshots from the Lichess Opening Explorer
for each configured opening and persist a consolidated raw JSON per ECO.

**Interface:**
```
CLI    : --eco <ECO> --from 2023-01 --to 2026-04 --rating 2000 --speed blitz
           --max-skipped-ratio 0.4
OUTPUT : writes/updates data/raw/{ECO}.json
         { "months": [ { "month": "YYYY-MM", ... } ], "_meta": { "skipped_months": [...] } }
EARLY-STOP: if below-min months / total months exceeds --max-skipped-ratio,
            deletes partial raw file and exits immediately
```

**MonthFetchOutcome enum:**
| Variant | Meaning |
|---|---|
| `Fetched` | Month written to consolidated file |
| `BelowMin` | Games below min threshold — counted toward skip ratio |
| `Skipped` | Month already present in file — not refetched |
| `Error` | HTTP or parse failure |

**Crates:**
| Crate | Purpose |
|---|---|
| `tokio` | Async runtime |
| `reqwest` | HTTP client |
| `serde` / `serde_json` | JSON deserialization |
| `clap` | CLI argument parsing |

**Rate limiting:** 1-second sleep between requests. User-Agent derives from `CARGO_PKG_VERSION`.

---

### `scripts/temp_bootstrap_openings.py` — Bootstrap orchestrator

**Responsibility:** Activate and fetch ECO batches from the catalog, track completion,
and prune failed/low-coverage openings.

**Interface:**
```
CLI : --apply --eco-offset N --limit M --dry-run
```

**Per-ECO workflow:**
1. Call Rust fetcher subprocess for the ECO
2. Classify result: `tier1`, `tier2`, `pruned_tier3`, `no_file`, `error`, …
3. Mark terminal statuses immediately in `openings_catalog.csv`:
   - `bootstrap_fetch_complete`, `bootstrap_fetched_until`, `bootstrap_fetch_status`
4. Cleanup: remove empty/below-min marker raw files

**Terminal statuses** (not re-fetched on reruns): `pruned_tier3`, `no_file`, `error_terminal`

---

### `src/ingest.py` — Python

**Responsibility:** Parse consolidated raw JSONs into a single normalized time series CSV.

**Interface:**
```
INPUT  : data/raw/{ECO}.json  (months array + _meta.skipped_months)
OUTPUT : data/processed/openings_ts.csv
```

**Output schema:**
```
month | eco | opening_name | rating_bracket | white | draws | black | total | white_win_rate
```

**Key logic:**
- Loop all raw JSON files, read `months` array
- Compute `white_win_rate = white / (white + draws + black)`
- Drop rows where `total < 500` — statistically unreliable months
- Flag months where `total < 2000` with a `low_confidence` boolean column

---

### `src/select_openings.py` — Python

**Responsibility:** Compute per-ECO selection flags and model tiers from time series
data and merge them into `data/openings_catalog.csv`.

**Interface:**
```
INPUT  : data/processed/openings_ts.csv
         data/openings_catalog.csv
OUTPUT : data/openings_catalog.csv (updated in-place)
         data/selection_flags.csv
```

**Selection rules:**
- `is_tracked_core = True` if `avg_monthly_games ≥ 1000` AND `months_with_data ≥ 24`
- `is_long_tail = True` if `avg_monthly_games ≥ 100` AND NOT `is_tracked_core`
- `model_tier = 1` if `is_tracked_core`
- `model_tier = 2` if `is_long_tail` AND `avg_monthly_games ≥ 500`
- `model_tier = 3` if `is_long_tail` AND `avg_monthly_games < 500`

---

### `src/timeseries.py` — Python (primary differentiator)

**Responsibility:** Fit models on monthly win rate series and forecast 3 months
ahead. Dispatches to different model tiers based on opening data volume.

**Interface:**
```
INPUT  : data/processed/openings_ts.csv
         data/openings_catalog.csv
OUTPUT : data/output/forecasts.csv
```

**Output schema:**
```
eco | opening_name | month | actual | forecast | lower_ci | upper_ci | is_forecast | structural_break | model_tier
```

**Tier structure:**

| Tier | Model | Extras | Condition |
|---|---|---|---|
| 1 | ARIMA (auto, AIC) | Chow break test + Ljung-Box | `model_tier == 1` |
| 2 | Holt-Winters (`trend='add'`, no seasonality) | CI = ±1.96 × residual std | `model_tier == 2` |
| 3 | Skipped | Descriptive stats only (logged) | `model_tier == 3` |

**Libraries:** `pmdarima`, `statsmodels`, `pandas`, `numpy`

---

### Model Selection & Diagnostic Fallback

**Problem:** ARIMA order selection via AIC can produce an ARIMA(0,0,0) white-noise
model even when the time series exhibits autocorrelated structure. This occurs
especially on shorter or high-variance series where AIC favors parsimony. Publishing
such misspecified forecasts undermines confidence in the predictions.

**Detection:** After fitting the ARIMA model, `timeseries.py` runs the Ljung-Box
test on residuals (`statsmodels.stats.diagnostic.acorr_ljungbox`, lags=10, α=0.05).
- If p-value < 0.05, residuals are autocorrelated → model is misspecified
- If p-value ≥ 0.05, residuals are white noise → model is valid

**Three-case dispatch** (implemented in Tier-1 loop, ~line 190–240):

1. **ARIMA(0,0,0) + p < 0.05 (true misspecification)**
   - Action: Fall back to Holt-Winters (Tier-2 model)
   - Output: `model_tier_override = "tier1_hw_fallback"`, `forecast_quality = "low"`
   - Rationale: (0,0,0) is white noise; if test rejects, underlying structure exists;
     HW captures trend/level without requiring MA/AR tuning
   - Example: ECO A16 (Sicilian, 1.g3) had ARIMA(0,0,0) with Ljung-Box p=0.005;
     fallback applied; forecast quality flagged as `low`

2. **ARIMA(p≥1 or q≥1) + p < 0.05 (partial capture)**
   - Action: Keep ARIMA forecast but mark quality as low
   - Output: `model_tier_override = None`, `forecast_quality = "low"`
   - Rationale: AR/MA coefficients exist but residuals still autocorrelated;
     likely short-run dynamics not fully captured; signal uncertainty to downstream consumers
   - Example: ECO B22 (Sicilian Closed, 2.Nc3) had ARIMA(0,0,1) with p=0.047;
     kept ARIMA but marked `forecast_quality = "low"`

3. **Any ARIMA order + p ≥ 0.05 (no conflict)**
   - Action: Normal path
   - Output: `model_tier_override = None`, `forecast_quality = "normal"`
   - Rationale: Residuals white noise; model specification is sound

**Output schema extension:**
```
... existing columns ...
| forecast_quality | model_tier_override
```
- `forecast_quality ∈ {"normal", "low"}` — signals forecast reliability
- `model_tier_override ∈ {None, "tier1_hw_fallback"}` — explains non-standard model choice

**Validation:** Real run (2026-04 snapshot) processed 11,940 forecast rows:
- 86 rows triggered tier1_hw_fallback (e.g., A16, E97)
- 129 rows marked forecast_quality=low (e.g., B22)
- Remaining 11,725 rows returned forecast_quality=normal

---

### `src/engine_delta.py` — Python (secondary differentiator)

**Responsibility:** Evaluate each opening's position after move 8 with Stockfish,
convert centipawn score to theoretical win probability, and compute delta against
actual human win rates.

**Interface:**
```
INPUT  : openings.json (ECO → FEN after move 8)
         data/processed/openings_ts.csv (for human win rates at 2000+ bracket)
         data/openings_catalog.csv
OUTPUT : data/output/engine_delta.csv
```

**Output schema:**
```
eco | opening_name | engine_cp | p_engine | human_win_rate_2000 | delta | interpretation
```

**Tier filtering:** Only evaluates ECOs with `model_tier == 1`.

**Centipawn → probability conversion:**
$$P_{engine}(cp) = \frac{1}{1 + e^{-cp/400}}$$

**Delta interpretation:**
- `delta > 0.04` : humans outperform engine prediction
- `delta < -0.04` : opening systematically misplayed
- `|delta| < 0.04` : consistent with engine evaluation

**Stockfish interface:** UCI subprocess via `python-stockfish` wrapper, depth 20, hash 256MB.

---

### `src/report.py` — Python (Groq-powered)

**Responsibility:** Generate findings.md, findings.json, and narratives.json using
Groq's `llama-3.1-8b-instant` model, with a templated fallback when the API is unavailable.

**Interface:**
```
INPUT  : data/output/forecasts.csv
         data/output/engine_delta.csv
OUTPUT : findings/findings.md
         findings/findings.json
         findings/narratives.json  (per-ECO, merged incrementally)
```

**Groq model:** `llama-3.1-8b-instant`
- RPM: 30, RPD: 14,400
- TPM: 6,000, TPD: 500,000

**Rate-limit strategy:**
- Call 1: Main `findings.json` with condensed data (top-5/bottom-5 delta + forecast summary)
- Calls 2+: Per-opening narratives in batches of `NARRATIVE_BATCH_SIZE=8` openings
- 22-second sleep between narrative batches to stay within 6K TPM
- Exponential backoff on 429 errors (up to 3 retries)

**`findings.json` schema:**
```json
{
  "generated_at": "YYYY-MM-DD",
  "month": "YYYY-MM",
  "headline": "...",
  "panels": {
    "forecast": { "insight": "...", "highlight_ecos": ["ECO1"] },
    "engine_delta": { "insight": "...", "outliers": ["ECO1"] },
    "heatmap": { "insight": "..." }
  }
}
```

**`narratives.json` contract (per-opening, used by visualizer):**
```json
{ "per_opening": { "B20": "narrative text ...", ... } }
```

---

### `src/visualizer.py` + `src/dashboard/*` — Python

**Responsibility:** Generate a multi-page static HTML site from output CSVs.
`src/visualizer.py` is a stable public facade; implementation lives in `src/dashboard/`.

**Interface:**
```
INPUT  : data/output/forecasts.csv
         data/output/engine_delta.csv
         data/openings_catalog.csv
         findings/findings.json          (optional; graceful degradation if absent)
         findings/narratives.json        (optional)
OUTPUT : data/output/dashboard/
```

**Page structure:**

| File | Purpose |
|---|---|
| `index.html` | Overview: headline insights from findings.json + 3 Plotly panels |
| `openings.html` | Searchable/sortable/filterable table of all openings |
| `families.html` | ECO family summary (A–E) with avg win rate |
| `opening.html` | Per-opening detail: Plotly forecast, engine box, AI narrative (?eco=B20) |
| `assets/shared.css` | Design tokens, nav, table, widget component styles |
| `assets/nav.js` | Active-link highlight script |
| `assets/opening.js` | Per-opening interactive view logic |

**Internal package structure (`src/dashboard/`):**

| Module | Purpose |
|---|---|
| `builder.py` | Orchestrates all dashboard outputs and static asset copy steps |
| `data_access.py` | Shared path constants, JSON/CSV loaders, openings-data serialization |
| `charts.py` | Plotly figure construction for overview/families panels |
| `tokens.py` | Shared design tokens and Plotly typography helpers |
| `shell.py` | Shared page shell and navigation fragments |
| `pages/*` | Per-page renderers (`overview`, `openings`, `families`, `opening_template`) |

---

### `main.py` — Orchestrator

**Responsibility:** Run all pipeline stages in order with stage-skipping if output
already exists.

**Stage flags:**
```python
STAGES = {
    "fetch"   : False,  # set True to re-fetch from Lichess
    "ingest"  : True,
    "select"  : True,
    "ts"      : True,
    "engine"  : True,
    "viz"     : True,
    "report"  : True,
}
```

---

### `openings.json` — Seed Config

**Schema:**
```json
[
  {
    "eco": "B20",
    "name": "Sicilian Defense",
    "fen_move8": "<FEN string after 8 moves of mainline>",
    "mainline_moves": "e4 c5 Nf3 d6 d4 cxd4 Nxd4 Nf6 Nc3"
  }
]
```

Used by `engine_delta.py` for Stockfish FEN evaluation. The full catalog is driven
by `data/openings_catalog.csv` (498 ECO codes).

---

## Dependencies

### Rust (`Cargo.toml`)
```toml
[dependencies]
tokio = { version = "1", features = ["full"] }
reqwest = { version = "0.12", features = ["json"] }
serde = { version = "1", features = ["derive"] }
serde_json = "1"
clap = { version = "4", features = ["derive"] }
```

### Python (`requirements.txt`)
```
pandas
numpy
pmdarima
statsmodels
plotly
stockfish
python-chess
scipy
groq
python-dotenv
```

---

## Known Constraints

| Constraint | Mitigation |
|---|---|
| Lichess Explorer throttles aggressive requests | 1s sleep in Rust fetcher |
| Months with < 500 games give unreliable win rates | Drop in ingest.py |
| ARIMA requires ≥ 24 data points per opening | Fetch from 2023-01 → 2026-04 (40 months) |
| Stockfish must be installed locally | Document path config in README |
| Opening Explorer FENs must match mainline exactly | Validate FENs in openings.json against Lichess Explorer UI |
| Opening catalogue coverage | openings_catalog.csv drives all pipeline stages; openings absent from it are silently ignored |
| Engine delta CI budget | Total Stockfish evaluation must complete in < 5 min; warning logged if exceeded |
| Timeseries per-ECO budget | Each ECO must complete in < 60s; warning logged if exceeded |
| Groq TPM limit (6K/min) | Per-opening narrative batches of 8, 22s sleep between batches |
| GitHub Pages root path | deploy.yml uploads `data/output/dashboard/`; `index.html` is the Pages entry point |
