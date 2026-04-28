# OpenCast — Chess Opening Analytics

> ARIMA time-series forecasting of chess opening win rates, with Stockfish engine-delta analysis across 20 ECO openings on Lichess 2000-rated blitz games (2023-01 → 2026-03).

---

## Hypothesis

At 2000-rated blitz, human win rates for a given opening should track closely to the theoretical win probability implied by Stockfish's centipawn evaluation. Openings with large negative deltas (human rate << engine prediction) are either theory-heavy (humans misplay them) or have hidden defensive resources that keep games close. Structural breaks in the monthly win-rate time series signal shifts in community understanding — arising from viral YouTube content, top-player broadcast games, or engine-assisted preparation becoming mainstream.

---

## Pipeline

```
Lichess Explorer API → Rust Fetcher → data/raw/
  → Python Ingestor  → data/processed/openings_ts.csv
  → ARIMA Module     → data/output/forecasts.csv
  → Engine Delta     → data/output/engine_delta.csv
  → Visualizer       → data/output/dashboard.html
```

**Run everything:**
```bash
export LICHESS_TOKEN=<your_token>
pip install -r requirements.txt
python main.py
```

**Run individual stages:**
```bash
(cd fetcher && cargo run -- --from 2023-01 --to 2026-03 --rating 2000 --speed blitz)
python -m src.ingest
python -m src.timeseries
python -m src.engine_delta
python -m src.visualizer
```

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
