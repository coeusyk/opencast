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
  [Visualizer]  ──── 3-panel Plotly HTML dashboard
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
│   └── output/
│       ├── forecasts.csv      ← ARIMA forecasts with confidence intervals
│       └── engine_delta.csv   ← centipawn vs human win rate delta per opening
│
├── src/
│   ├── __init__.py
│   ├── ingest.py              ← reads data/raw/ JSONs → openings_ts.csv
│   ├── timeseries.py          ← ARIMA fitting, forecasting, structural break detection
│   ├── engine_delta.py        ← Stockfish eval → delta computation
│   └── visualizer.py          ← Plotly 3-panel dashboard (exports .html)
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

---

### `src/timeseries.py` — Python (primary differentiator)

**Responsibility:** Fit ARIMA models on monthly win rate series and forecast
3 months ahead. Detect structural breaks (regime changes in opening popularity).

**Interface:**
```
INPUT  : data/processed/openings_ts.csv
OUTPUT : data/output/forecasts.csv
```

**Output schema:**
```
eco | opening_name | month | actual | forecast | lower_ci | upper_ci | is_forecast
```

**Pipeline per opening:**
1. Extract monthly `white_win_rate` series (min 24 data points required)
2. ADF test for stationarity — first-difference if non-stationary (d=1)
3. Fit `ARIMA(p,d,q)` via `pmdarima.auto_arima` (information criterion: AIC)
4. Forecast 3 months ahead with 95% confidence intervals
5. Structural break detection via `statsmodels` Chow test at each month
6. Ljung-Box test on residuals — log warning if autocorrelation remains

**Libraries:** `pmdarima`, `statsmodels`, `pandas`, `numpy`

**Mathematical note:** Win probability from engine centipawn score uses the
standard sigmoid transformation applied in engine delta module (see below).

---

### `src/engine_delta.py` — Python (secondary differentiator)

**Responsibility:** Evaluate each opening's position after move 8 with Stockfish,
convert centipawn score to theoretical win probability, and compute delta against
actual human win rates.

**Interface:**
```
INPUT  : openings.json (ECO → FEN after move 8)
         data/processed/openings_ts.csv (for human win rates at 2000+ bracket)
OUTPUT : data/output/engine_delta.csv
```

**Output schema:**
```
eco | opening_name | engine_cp | p_engine | human_win_rate_2000 | delta | interpretation
```

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

**Responsibility:** Produce a 3-panel Plotly HTML dashboard from output CSVs.

**Interface:**
```
INPUT  : data/output/forecasts.csv, data/output/engine_delta.csv
OUTPUT : data/output/dashboard.html
```

**Panel 1 — Forecast chart (line + shaded CI)**
- X: month, Y: white_win_rate
- Solid line for actuals, dashed for forecast, shaded band for 95% CI
- One trace per opening (5 openings max for readability)
- Annotate detected structural breaks with vertical dashed lines

**Panel 2 — Engine delta scatter (bubble chart)**
- X: engine centipawn score, Y: human win rate at 2000+
- Diagonal reference line = "engine-expected" win rate
- Bubble size = total game volume; color = ECO category (A/B/C/D/E)
- Openings above the line: human skill amplifiers
- Openings below the line: theory-heavy, engine-correct

**Panel 3 — ECO heatmap by rating bracket**
- Y: ECO category (A/B/C/D/E), X: rating bucket (1200/1500/1800/2000/2200/2500)
- Cell value: average white_win_rate
- Color scale: diverging Red-White-Green centered at 0.50
- Reveals which opening categories only work at low ELO

---

### `main.py` — Orchestrator

**Responsibility:** Run all pipeline stages in order with stage-skipping if output
already exists (avoid re-fetching).

**Stage flags:**
```python
STAGES = {
    "fetch"   : True,   # set False after first run
    "ingest"  : True,
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
