# OpenCast — Copilot Instructions

## Stack
- Rust (fetcher/): tokio async, reqwest, serde, clap
- Python (src/): pandas, pmdarima, statsmodels, plotly, python-stockfish
- WSL2 Ubuntu, VS Code Remote WSL

## Project layout
- fetcher/ is a Cargo workspace binary (opencast-fetcher)
- src/ contains Python pipeline modules (ingest, timeseries, engine_delta, visualizer)
- data/raw/ = Rust output, data/processed/ = Python input, data/output/ = final artifacts

## Conventions
- Rust: snake_case, explicit error types (no unwrap() in production paths, use ?)
- Python: type hints on all function signatures, no bare except
- All file writes go through the data/ directory hierarchy — never to project root