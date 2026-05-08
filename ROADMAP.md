# OpenCast Roadmap

## Phase A — Opening Universe & Selection

- Catalogue full ECO range (498 ECO codes) → `data/openings_catalog.csv` (#19)
- Data-driven selection flags: `is_tracked_core`, `is_long_tail`, `model_tier` (#19)
- Catalog-driven fetcher — ECO list read from catalog, not hardcoded (#20)
- Long-tail descriptive stats (`long_tail_stats.csv`) for Tier-3 openings (#22)

## Phase B — Scalable Modeling Tiers

- Tier 1/2/3 dispatch in `timeseries.py` — ARIMA / Holt-Winters / descriptive (#21)
- `engine_delta.py` restricted to Tier-1 openings (#21)
- CI timing guardrails: `MAX_TIER1_OPENINGS` warning, per-ECO budget logging (#21)

## Phase C — Modular Dashboard

- Multi-page static site: `index.html`, `openings.html`, `families.html`, `opening.html`
- Per-opening detail pages with Plotly forecast chart, engine eval, AI narrative (#17)
- Openings table — search, filter (ECO group / model tier), sort, URL-hash state (#30)
- Insight widget grid on overview page — Summary / Forecasts / Engine Delta / Heatmap (#15, #31)
- Narrative box hidden when no analysis available (#16)
- Tier-3 opening detail page — stats-only, no chart, no engine eval (#29)
- Font system: Inter (body) + Instrument Serif (display) (#14)

## Phase D — Infrastructure

- Separate `findings/narratives.json` for per-opening narratives (merge, not overwrite) (#18)
- Per-opening narrative generation in `report.py` Groq prompt (#17)
- Two-job CI workflow — `fetch` commits raw data before `process` runs (#26)
- `FETCH_START` single source of truth in `config.json` (#26)
- Incremental narrative generation — only regen ECOs with new data (#18)
- Strip historical phases from `ARCHITECTURE.md`; keep timeless design docs (#27)

## Phase E — Future

- Incremental fetch: fetch and commit only the new month, not full history re-check
- FETCH_START auto-advance: derive from the oldest gap in `data/raw/`
- Bootstrap tooling for new ECO batches (`scripts/temp_bootstrap_openings.py`)
- GitHub Pages deploy via `deploy.yml` — push `data/output/dashboard/` as Pages root
