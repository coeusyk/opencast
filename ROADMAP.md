# OpenCast — Roadmap

This file tracks planned work. ARCHITECTURE.md is the stable design
reference; this file is the versioned plan.

***

## Phase A — Opening Universe & Selection
- Introduce `openings_catalog.csv` as the canonical opening list
- Make the Rust fetcher and Python pipeline drive from the catalogue
- Define data-driven selection criteria for "core tracked" openings
- Generate aggregated stats for long-tail openings

## Phase B — Scalable Modeling Tiers
- Assign model tiers (1/2/3) per opening based on volume and stability
- Tier 1: current ARIMA + Chow + engine delta (core openings only)
- Tier 2: lighter models (Holt-Winters or rolling trend), no break tests
- Tier 3: descriptive stats only
- Add CI timing guardrails to prevent runaway runtimes

## Phase C — Modular Dashboard
- Replace single dashboard.html with a multi-page static site structure
- Pages: overview (index.html), openings table, per-opening detail, families
- Surface findings.json insights as headline widgets on the overview page
- Link structure between all pages with a shared navigation bar

## Phase D — Architecture Docs Cleanup
- Strip historical Phase 1–7 task breakdown from ARCHITECTURE.md
- Add this ROADMAP.md
