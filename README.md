# OpenCast — Chess Opening Analytics

OpenCast is a data pipeline that fetches monthly win-rate snapshots for 20 ECO openings from the Lichess Opening Explorer API, fits per-opening ARIMA time series models to detect structural breaks and forecast future win rates, and computes an engine-human delta score — the gap between Stockfish's theoretical win probability and the actual human win rate at 2000-rated blitz. Unlike a standard win-rate dashboard, OpenCast surfaces *where humans systematically diverge from engine expectation* and *whether those patterns are accelerating or reversing*.

---

## Live Dashboard

[https://coeusyk.github.io/opencast/dashboard.html](https://coeusyk.github.io/opencast/dashboard.html)

---

## Latest Findings

See [FINDINGS.md](FINDINGS.md) — auto-generated monthly by the pipeline.

---

## How It Works

1. **Fetch** — A Rust binary queries `explorer.lichess.ovh` month-by-month for each opening, writing one JSON file per opening per month into `data/raw/`.
2. **Ingest** — Python normalises all JSONs into `data/processed/openings_ts.csv` (780 rows, one per opening × month).
3. **Analyse** — `timeseries.py` fits `auto_arima` models (AIC) per opening, runs Ljung-Box and Chow structural-break tests, and writes 3-month forecasts with 95% CI to `data/output/forecasts.csv`. `engine_delta.py` evaluates each opening with Stockfish at depth 20 and writes the engine-vs-human delta to `data/output/engine_delta.csv`.
4. **Report & Visualise** — `report.py` generates `FINDINGS.md` (LLM-powered via Ollama, with template fallback). `visualizer.py` renders a 3-panel Plotly dashboard: forecast ribbons for the top-5 openings by volume, a bubble chart of engine cp vs human win rate, and an ECO × month win-rate heatmap.

---

## Setup

```bash
git clone https://github.com/coeusyk/opencast.git
cd opencast

# Lichess API token (free at https://lichess.org/account/oauth/token)
export LICHESS_TOKEN=<your_token>

# Build the Rust fetcher
cd fetcher && cargo build --release && cd ..

# Install Python dependencies
pip install -r requirements.txt

# Run the full pipeline
python main.py
```

> **Stockfish 16** must be installed separately: `sudo apt install stockfish`

> **Ollama** (optional, for LLM-generated findings): install from [ollama.com](https://ollama.com) and run `ollama pull qwen3:0.6b`. If unavailable, `report.py` falls back to templated text.

---

## Data Coverage

| Metric | Value |
|---|---|
| Openings tracked | 20 (ECO A–E) |
| Date range | 2023-01 → 2026-03 (39 months) |
| Raw JSON files | 780 |
| Processed rows | 780 (all total ≥ 500 games) |
| Forecast rows | 840 (780 actual + 60 forecast, 3 months per opening) |
| Total games analysed | ~123 million |

---

## Engine-Human Delta Findings

Stockfish (depth 20) evaluates each opening's position and the implied win probability is compared to the observed human win rate at 2000-rated blitz. Delta = human rate − engine prediction.

### Engine-favoured openings (delta < −0.04) — frequently misplayed

| ECO | Opening | Engine cp | P_engine | Human WR | Delta |
|---|---|---|---|---|---|
| D70 | Grünfeld Defense | +51 | 0.5318 | 0.4674 | **−0.0644** |
| B01 | Scandinavian Defense | +64 | 0.5399 | 0.4818 | **−0.0581** |
| B07 | Pirc Defense | +60 | 0.5374 | 0.4817 | **−0.0558** |
| B06 | Modern Defense | +64 | 0.5399 | 0.4873 | **−0.0526** |
| E60 | King's Indian Defense | +61 | 0.5381 | 0.4880 | **−0.0501** |
| C20 | King's Gambit | +43 | 0.5268 | 0.4803 | **−0.0465** |
| B20 | Sicilian Defense | +44 | 0.5275 | 0.4827 | **−0.0447** |
| C00 | French Defense | +45 | 0.5281 | 0.4858 | **−0.0423** |

The Grünfeld (−0.0644) shows the largest gap: Stockfish scores White at +51 cp, yet humans only achieve 0.4674 win rate — suggesting that Black's dynamic counterplay in the Grünfeld is reliably mishandled at this rating. The Scandinavian's White advantage (+64 cp) is rarely converted, hinting that Black's simplified structure is easier to play in practice than theory suggests.

### Consistent openings (|delta| ≤ 0.04)

The classical openings — **Italian Game (C50)**, **Ruy Lopez (C60)**, **London System (D00)**, **Queen's Gambit (D06)**, **QGD (D30)**, **Nimzo-Indian (E20)**, **English (A10)**, and **Trompowsky (A45)** — all land within ±0.04 of engine expectation. No opening showed humans *outperforming* the engine at 2000-rated blitz; the closest were Queen's Gambit (+0.0303) and Ruy Lopez (+0.0190).

---

## ARIMA Forecasting & Structural Breaks

All 20 openings were modelled with `auto_arima` (AIC criterion, max p/q = 3). All models passed the Ljung-Box residual test (no remaining autocorrelation at lag 10). Forecasts extend 3 months beyond the data window with 95% confidence intervals.

### Notable structural breaks

**C44 — King's Pawn Game (17 breaks)**  
Sustained regime shift from 2024-09 onward — 13 consecutive months flagged. Likely reflects the explosion of the King's Pawn game at intermediate rating after prominent streamers adopted 1.e4 setups. Win rates show a mild upward drift through 2025.

**B06 — Modern Defense (12 breaks, 2024-05 → 2025-05)**  
A continuous 12-month structural break window in the Modern Defense coincides with a period of increased hypermodern content on major chess platforms. White's win rate contracted noticeably before recovering.

**D06 — Queen's Gambit (8 breaks: 2024-03–07 and 2025-09–11)**  
Two distinct break clusters suggest two separate events influenced the Queen's Gambit at 2000-rated blitz — possibly top-level tournament games in early 2024 and again in late 2025.

**E60 — King's Indian Defense (6 breaks: 2024-11 → 2025-09)**  
The KID shows ongoing regime instability from late 2024, with win rate volatility increasing — consistent with the opening's reputation as double-edged and theory-dependent.

**B07 — Pirc Defense (6 breaks: 2024-08 → 2025-06)**  
Win rate for White rises through this period, suggesting the blitz community learned to exploit the Pirc's slow development more effectively.

**D70 — Grünfeld Defense (2 breaks: 2023-12, 2025-05)**  
Despite just two break points, the Grünfeld has the largest negative engine-delta (−0.0644). Both breaks correspond to sharp drops in White's win rate — perhaps periodic rebalancing as players discover Black's drawing resources.

---

## Architecture

See [ARCHITECTURE.md](ARCHITECTURE.md) for full module specifications, data schemas, and mathematical derivations.

---

## Requirements

- **Rust** ≥ 1.75 (stable) — for the Lichess fetcher  
- **Python** ≥ 3.11 — for analytics pipeline  
- **Stockfish 16** — `sudo apt install stockfish` (or set `STOCKFISH_PATH`)  
- **Lichess OAuth token** — free at https://lichess.org/account/oauth/token  
- **Ollama** (optional) — `ollama pull qwen3:0.6b` for LLM-generated findings

```bash
pip install -r requirements.txt
```

---

## Repository Structure

```
fetcher/          ← Rust binary (Lichess Explorer → JSON)
src/
  ingest.py       ← JSON → openings_ts.csv
  timeseries.py   ← ARIMA forecasting + break detection
  engine_delta.py ← Stockfish centipawn → win probability delta
  visualizer.py   ← 3-panel Plotly HTML dashboard
data/
  raw/            ← 780 JSON files (gitignored)
  processed/      ← openings_ts.csv
  output/         ← forecasts.csv, engine_delta.csv, dashboard.html
openings.json     ← 20 ECO codes with UCI move sequences
main.py           ← pipeline orchestrator
```
