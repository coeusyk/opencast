# OpenCast — Architecture

## Project Goal

Forecast chess opening win rate trajectories using ARIMA time series modeling,
and quantify the gap between engine-theoretical win probability and actual human
performance across rating brackets. Two differentiators over existing Lichess
analytics projects:

1. **ARIMA forecasting** on monthly win rate time series per opening
2. **Engine-human delta** — Stockfish centipawn eval vs actual human win rate

---

## Data Flow

```
Lichess Opening Explorer API
  (queried month-by-month via since/until params)
        │
        ▼
  [Rust Fetcher]  ──── raw JSON per opening per month ────▶  data/raw/
        │
        ▼
  [Python Ingestor]  ── normalized DataFrame ──────────────▶  data/processed/openings_ts.csv
        │
        ├──▶ [ARIMA Module]  ──── forecasts + trend breaks ──▶  data/output/forecasts.csv
        │
        └──▶ [Engine Delta Module]
                  │
              Stockfish (UCI)  ◀── FEN after move 8 of each opening
                  │
              centipawn scores ──▶  data/output/engine_delta.csv
        │
        ▼
  [Visualizer]  ──── multi-page static site (data/output/dashboard/)
```

**Key API constraint:** Lichess Explorer supports `since` and `until` as `YYYY-MM`
query params — monthly snapshots without touching multi-GB PGN dumps.

---

## File Structure

```
opencast/
│
├── fetcher/                   ← Rust binary
│   ├── src/
│   │   ├── main.rs            ← CLI entry: takes opening FEN + date range
│   │   ├── client.rs          ← reqwest HTTP logic
│   │   └── models.rs          ← serde structs for API response
│   └── Cargo.toml
│
├── data/
│   ├── raw/                   ← JSON files from Rust fetcher (one per opening/month)
│   ├── processed/
│   │   └── openings_ts.csv    ← (month, eco, opening_name, rating, white, draws, black, total)
│   ├── openings_catalog.csv   ← canonical opening catalogue with tier flags
│   └── output/
│       ├── forecasts.csv      ← ARIMA / HW forecasts with confidence intervals
│       ├── engine_delta.csv   ← centipawn vs human win rate delta per opening
│       ├── long_tail_stats.csv ← descriptive stats for long-tail openings
│       └── dashboard/         ← multi-page static site (served as GitHub Pages)
│           ├── index.html     ← overview: headline insights + 3 panels
│           ├── openings.html  ← sortable table of all openings
│           ├── families.html  ← ECO family summary
│           ├── opening_*.html ← per-opening detail pages (one per ECO)
│           └── assets/
│               ├── shared.css ← design tokens, nav, table, widget styles
│               └── nav.js     ← active-link highlight script
│
├── src/
│   ├── __init__.py
│   ├── ingest.py              ← reads data/raw/ JSONs → openings_ts.csv
│   ├── select_openings.py     ← computes selection flags and model tiers
│   ├── timeseries.py          ← ARIMA (Tier 1) + Holt-Winters (Tier 2) + break detection
│   ├── engine_delta.py        ← Stockfish eval → delta computation (Tier 1 only)
│   ├── visualizer.py          ← multi-page static site generator
│   └── assets/
│       ├── shared.css         ← design tokens + component styles (source)
│       └── nav.js             ← active-nav script (source)
│
├── openings.json              ← config: ECO codes to track + move-8 FENs
├── main.py                    ← orchestrator: runs all pipeline stages in order
├── requirements.txt
├── architecture.md            ← this file
└── README.md                  ← hypothesis + findings per opening
```

---

## Module Specifications

### `fetcher/` — Rust binary

**Responsibility:** Pull monthly win rate snapshots from the Lichess Opening Explorer
for each configured opening and persist raw JSON.

**Interface:**
```
STDIN  : none
CLI    : --from 2023-01 --to 2026-03 --rating 2000 --speed blitz
CONFIG : reads openings.json for ECO → FEN mapping
OUTPUT : writes data/raw/{eco}_{YYYY-MM}.json
```

**Crates:**
| Crate | Purpose |
|---|---|
| `tokio` | Async runtime |
| `reqwest` | HTTP client |
| `serde` / `serde_json` | JSON deserialization |
| `clap` | CLI argument parsing |

**Rate limiting:** 1-second sleep between requests via `tokio::time::sleep`.
Total load: 20 openings × 30 months = 600 requests ≈ 10 minutes one-time.

**Rust concepts exercised:** async/await, serde derive macros, Result propagation
with `?`, struct-based deserialization, file I/O with `std::fs`.

---

### `src/ingest.py` — Python

**Responsibility:** Parse all raw JSONs into a single normalized time series CSV.

**Interface:**
```
INPUT  : data/raw/*.json
OUTPUT : data/processed/openings_ts.csv
         data/output/long_tail_stats.csv
```

**Output schema:**
```
month | eco | opening_name | rating_bracket | white | draws | black | total | white_win_rate
```

**Key logic:**
- Loop all raw JSON files, extract `white`, `draws`, `black` counts
- Compute `white_win_rate = white / (white + draws + black)`
- Drop rows where `total < 500` — statistically unreliable months
- Flag months where `total < 2000` with a `low_confidence` boolean column
- After writing `openings_ts.csv`, compute long-tail stats from catalog and write `long_tail_stats.csv`

---

### `src/select_openings.py` — Python

**Responsibility:** Compute per-ECO selection flags and model tiers from time series
data and merge them into `data/openings_catalog.csv`.

**Interface:**
```
INPUT  : data/processed/openings_ts.csv
         data/openings_catalog.csv
OUTPUT : data/openings_catalog.csv (updated in-place)
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

**Per-ECO timing:** each ECO is timed with `time.perf_counter()`; a warning is
logged if a single ECO exceeds 60s.

**Summary log:**
```
Timeseries: N openings processed in X.Xs (Tier1: Xs avg, Tier2: Xs avg)
```

**Libraries:** `pmdarima`, `statsmodels`, `pandas`, `numpy`

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

**Timing guardrail:** Total evaluation time is measured; a warning is logged if it
exceeds 300s (5 min budget).

**Centipawn → probability conversion:**

```
P_engine(cp) = 1 / (1 + e^(-cp / 400))
```

A cp of 0 → 50% (equal). A cp of +100 (White advantage) → ~56%.

**Delta interpretation:**
- `delta > 0.04` : humans outperform engine prediction — opening rewards human skill
- `delta < -0.04` : opening objectively better than humans realize, or frequently misplayed
- `|delta| < 0.04` : consistent with engine evaluation

**Stockfish interface:** UCI subprocess via `python-stockfish` wrapper,
depth 20, hash 256MB.

---

### `src/visualizer.py` — Python

**Responsibility:** Generate a multi-page static HTML site from output CSVs.
All pages share a navigation bar and design token set.

**Interface:**
```
INPUT  : data/output/forecasts.csv
         data/output/engine_delta.csv
         data/openings_catalog.csv
         findings/findings.json          (optional; graceful degradation if absent)
OUTPUT : data/output/dashboard/          (directory; served as GitHub Pages root)
```

**Page structure:**

| File | Purpose |
|---|---|
| `index.html` | Overview: headline insights from findings.json + 3 Plotly panels |
| `openings.html` | Sortable table of all openings with last win rate and engine delta |
| `families.html` | ECO family summary (A–E) with avg win rate |
| `opening_{ECO}.html` | Per-opening detail: Plotly forecast, engine box, AI narrative |
| `assets/shared.css` | Design tokens, nav, table, widget component styles |
| `assets/nav.js` | Active-link highlight script |

**Render functions:**
- `render_overview(forecasts, engine_df, findings_json)` → `index.html`
- `render_openings_table(forecasts, engine_df, catalog)` → `openings.html`
- `render_families(forecasts)` → `families.html`
- `render_opening_page(eco, forecasts, engine_df, findings_json)` → `opening_{eco}.html`
- `run_visualizer()` — orchestrates all four renders + asset copy

**Design tokens** (preserved):
```python
PANEL_BG = "#121821"; GRID_COLOR = "rgba(148, 163, 184, 0.18)"; TEXT_PRIMARY = "#E6EEF8"
TEXT_SECONDARY = "#9FB0C3"; ACCENT = "#57C7FF"
ECO_COLORS = {"A":"#7CC7FF","B":"#7BE495","C":"#F6C177","D":"#F28DA6","E":"#B9A5FF"}
BODY_FONT = "'DM Sans', system-ui, sans-serif"
DISPLAY_FONT = "'DM Serif Display', Georgia, serif"
```

**`findings.json` contract for per-opening narratives:**
```json
{ "per_opening": { "B20": "narrative text ...", ... } }
```
Falls back to "No analysis available yet." if the key is absent.

---

### `main.py` — Orchestrator

**Responsibility:** Run all pipeline stages in order with stage-skipping if output
already exists (avoid re-fetching).

**Stage flags:**
```python
STAGES = {
    "fetch"   : True,   # set False after first run
    "ingest"  : True,
    "select"  : True,
    "ts"      : True,
    "engine"  : True,
    "viz"     : True,
}
```

---

### `openings.json` — Config

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

Covers 20 openings across ECO categories A–E, including:
Sicilian Defense, London System, King's Indian Defense, Caro-Kann,
Queen's Gambit Declined, Ruy Lopez, French Defense, King's Gambit,
Dutch Defense, English Opening.

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
python-stockfish
requests
```

---

## Known Constraints

| Constraint | Mitigation |
|---|---|
| Lichess Explorer throttles aggressive requests | 1s sleep in Rust fetcher |
| Months with < 500 games give unreliable win rates | Drop in ingest.py |
| ARIMA requires ≥ 24 data points per opening | Fetch from 2023-01 → 2026-03 (27 months) |
| Stockfish must be installed locally | Document path config in README |
| Opening Explorer FENs must match mainline exactly | Validate FENs in openings.json against Lichess Explorer UI |
| Opening catalogue coverage | openings_catalog.csv drives all pipeline stages; openings absent from it are silently ignored |
| Engine delta CI budget | Total Stockfish evaluation must complete in < 5 min; warning logged if exceeded |
| Timeseries per-ECO budget | Each ECO must complete in < 60s; warning logged if exceeded |
| GitHub Pages root path | deploy.yml uploads `data/output/dashboard/`; `index.html` is the Pages entry point |
