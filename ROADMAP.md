# OpenCast Roadmap

This file tracks the high-level feature roadmap, organised by phase. Day-level
delivery details live in GitHub Issues. See [ARCHITECTURE.md](ARCHITECTURE.md)
for system design context.

---

## Phase A — Opening Universe & Selection

Catalogue the full ECO range and introduce data-driven selection flags so the
pipeline scales beyond a hand-maintained list of 20 openings.

- Catalogue full ECO A–E range in `data/openings_catalog.csv`
- Data-driven selection flags: `is_tracked_core`, `is_long_tail`, `model_tier`
- Selection criteria: avg monthly games ≥ threshold, ≥ 24 months data
- Long-tail descriptive stats for all Tier-3 openings

Relevant issues: [#19](https://github.com/coeusyk/opencast/issues/19), [#22](https://github.com/coeusyk/opencast/issues/22)

---

## Phase B — Scalable Modeling Tiers

Dispatch analysis to the right model based on volume and data depth, so CI
stays fast as the tracked set grows.

- Tier 1 / 2 / 3 dispatch in `timeseries.py` (ARIMA / Holt-Winters / descriptive)
- Engine delta restricted to Tier-1 openings only
- CI timing guardrail: `MAX_TIER1_OPENINGS = 50`, hard cap at 100

Relevant issues: [#21](https://github.com/coeusyk/opencast/issues/21)

---

## Phase C — Modular Dashboard

Ship the multi-page dashboard and fill in the remaining UX gaps.

- Multi-page structure: Overview, Openings table, Families, per-opening detail
- Tier-3 stats-only detail page (no chart, no engine box)
- Openings table: search, filter by ECO group / tier, sortable columns
- Overview insight widgets in 2-column grid
- Narrative box hidden when no analysis is available

Relevant issues: [#15](https://github.com/coeusyk/opencast/issues/15), [#16](https://github.com/coeusyk/opencast/issues/16), [#29](https://github.com/coeusyk/opencast/issues/29), [#30](https://github.com/coeusyk/opencast/issues/30), [#31](https://github.com/coeusyk/opencast/issues/31)

---

## Phase D — Infrastructure & Narrative Generation

Make the pipeline incremental, resilient, and AI-narrated.

- Incremental CI: fetch job commits `data/raw/` before process job starts
- `FETCH_START` as a single source of truth in `config.json`
- Catalog-driven Rust fetcher (replaces hard-coded opening list)
- Per-opening AI narratives in `report.py` (Groq-powered, Tier-1 priority)
- `findings/narratives.json` separate from `findings/findings.json`; merge strategy prevents monthly overwrite

Relevant issues: [#17](https://github.com/coeusyk/opencast/issues/17), [#18](https://github.com/coeusyk/opencast/issues/18), [#20](https://github.com/coeusyk/opencast/issues/20), [#26](https://github.com/coeusyk/opencast/issues/26)
