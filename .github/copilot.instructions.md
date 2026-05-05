# OpenCast — Copilot Instructions

## Project Overview

OpenCast is a chess opening analytics pipeline. It ingests monthly Lichess
data, forecasts win-rate trends using ARIMA and Holt-Winters, measures
engine-human divergence via Stockfish evaluation, and publishes a modular
static dashboard.

**Repo:** github.com/coeusyk/opencast  
**Stack:** Rust (fetcher), Python (pipeline + dashboard), GitHub Actions (CI),
GitHub Pages (hosting)

---

## Core Principles

### 1. Never agree by default

Do not validate a request just because the user made it. Before implementing
anything, check whether the proposed change aligns with the architecture,
existing pipeline logic, and sound engineering practice.

If a proposed change is wrong, incomplete, or introduces a regression — say so
directly, explain why it fails, and propose the correct direction. Agreement
requires actual validation, not deference.

### 2. Read before acting

Before making any change, use MCP tools to read every file directly affected
by the task. Do not assume file content matches what was described. Do not rely
on memory of previous turns for file state — the file on the branch is the
ground truth.

Always read at minimum:
- The file(s) being changed
- Any file that imports or is imported by the changed file
- The relevant workflow YAML if CI is involved
- `config.json` and `openings_catalog.csv` if the change touches thresholds
  or opening selection

### 3. Use every MCP tool at your disposal

- `get_file_contents` — read source files before editing
- `create_or_update_file` — write changes
- `search_code` — find usages, cross-references, constants
- `list_commits`, `get_commit` — verify what was actually merged, not what
  was claimed
- `create_issue`, `create_pull_request` — for any non-trivial change
- `list_pull_requests`, `get_pull_request` — check PR status before assuming
  a branch is current

Never guess at file content, function signatures, or variable names. Look them
up.

### 4. Validate every claim

If the user says "X is done" or "X works" — verify it in the code. If the
user says "this is a small change" — read the affected surface area and decide
independently. If the user says "the tests pass" — check the workflow run
if possible.

---

## Architecture Ground Truths

These are invariants. Changes that violate them require explicit justification.

**Pipeline order:**  
`fetch` → `ingest` → `select` → `timeseries` → `engine_delta` → `report` → `visualize`

**Modeling tiers (from `openings_catalog.csv`):**
- Tier 1 — ARIMA + Chow structural break + Ljung-Box + engine delta
- Tier 2 — Holt-Winters, no break tests, no engine delta
- Tier 3 — descriptive stats only, no forecast output

**Threshold source of truth:** `config.json` — never hardcode thresholds that
exist there. If a module uses a hardcoded value that conflicts with config,
that is a bug.

**Dashboard is static:** `visualizer.py` generates HTML + JSON files. There is
no server. Plotly is loaded via CDN. All per-opening data is pre-serialized
into `assets/openings_data.json`.

**Single opening template:** `opening.html` is one file with query-param
routing (`?eco=B20`). Per-ECO HTML files are not generated.

**Trend signals come from `trend_classifier.py`:** The `TrendSignal` output
(slope, R², confidence, streak) must be serialized into `openings_data.json`
by `_serialize_openings_data()`. Groq/LLM receives these computed values — it
does not determine the trend itself.

**CI workflows run off `main`:** `update.yml` → `report.yml` → `deploy.yml`
are chained and operate on the `main` branch. `develop` is for code review
only.

---

## Code Standards

**Python:**
- All pipeline entry points follow the `run_<module>()` naming convention
- New thresholds belong in `config.json`, not as module-level constants
- `pd.read_csv` column access must be by name, not index
- DataFrame mutations must use `.copy()` to avoid chained assignment warnings
- Logging uses the module-level `log = logging.getLogger(__name__)` pattern

**JavaScript (dashboard):**
- No `localStorage` or `sessionStorage` — the dashboard runs in sandboxed
  iframes
- All interactive elements must have `:active` states for mobile tap feedback
- Hash-based filter state must not be double-encoded — pass the raw hash
  string, do not wrap in `encodeURIComponent`

**HTML/CSS:**
- Design tokens from `assets/shared.css` — no inline hex values in templates
- Font stack: Satoshi → Inter → system-ui
- Display font (Instrument Serif) only at `--text-xl` (24px) and above

---

## What Requires a PR

Any change that touches:
- `visualizer.py` output structure
- `openings_catalog.csv` schema
- `config.json` thresholds
- `forecasts.csv` schema (adding/removing columns)
- Any GitHub Actions workflow file

Trivial fixes (typos, comment corrections, single-variable renames) can be
committed directly to `develop`.

---

## Common Failure Modes to Check

Before shipping any change, verify these are not introduced:

1. **Threshold mismatch** — `select_openings.py` threshold matches
   `config.json`, not a hardcoded constant
2. **Double-encoded hash** — back-navigation filter state uses raw hash, not
   `encodeURIComponent`
3. **Trend label without signal** — `trend_direction` in `openings_data.json`
   must come from `TrendSignal`, not from Groq output
4. **Missing catalog fallback** — opening name lookups must fall back to
   `openings_catalog.csv` when `forecasts.csv` has a null or ECO-code-only
   name
5. **Structural break over-firing** — more than 3 `structural_break = True`
   months for a single opening in any 12-month window is a calibration issue
   in `timeseries.py`, not valid data
6. **`render_families()` drift** — this function must use `_page_shell()` and
   the same design tokens as the other pages; it is the most likely to fall
   behind during dashboard redesigns