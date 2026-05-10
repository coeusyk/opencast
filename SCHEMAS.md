# OpenCast Schemas

This document is the release contract for generated artifacts. If one of these schemas changes, update the owning module and the dashboard or CI consumer that reads it.

## CSV Artifacts

| Artifact | Owner | Required Columns | Notes |
|---|---|---|---|
| `data/processed/openings_ts.csv` | `src/ingest.py` | `month, eco, opening_name, rating_bracket, white, draws, black, total, white_win_rate, low_confidence` | One row per ECO-month. Rows below the configured minimum monthly game count are excluded. |
| `data/output/move_stats.csv` | `src/move_stats.py` | `eco, month, uci, san, games, white_win_rate, share_of_games, delta_share_12m, delta_wr_12m` | One row per ECO-month-move. Delta columns may be blank for the first 12 observations in a move series. |
| `data/output/forecasts.csv` | `src/timeseries.py` | `eco, opening_name, month, actual, forecast, lower_ci, upper_ci, is_forecast, structural_break, model_tier, forecast_quality, model_tier_override, model_name` | Historical rows keep `actual`; forecast rows keep the interval columns. |
| `data/output/engine_delta.csv` | `src/engine_delta.py` | `eco, opening_name, engine_cp, p_engine, human_win_rate_2000, delta, interpretation` | Tier-1 only. Missing or malformed move chains are skipped per opening. |
| `data/output/model_eval_summary.csv` | `src/model_eval.py` | `eco, model_name, horizon, mae_pp, rmse_pp, coverage_95, n_samples` | Offline evaluation output for Track 1 model selection. |

## JSON Artifacts

| Artifact | Owner | Required Shape | Notes |
|---|---|---|---|
| `data/output/model_choice.json` | `src/model_selection.py` | `{eco: {tier, model}}` | Per-ECO offline model choice. |
| `data/output/interval_calibration.json` | `src/model_selection.py` | `{model_name: {horizon: scale_factor}}` | Per-model, per-horizon interval-width calibration. |
| `data/opening_lines.json` | hand-maintained | `{eco: {lines: [{id, name, starting_fen, moves_san}]}}` | Curated opening lines for the interactive board. |
| `data/output/top_recommendations_*.json` | `src/opening_recommend.py` | `[{eco, name, score, delta, trend_slope}]` | Recommendation payload for the overview UI. |
| `data/output/vex_hook.csv` | `src/opening_recommend.py` or a helper script | `eco, representative_fen, engine_human_delta, trend_class` | Bridge artifact for future engine-analysis work. |

## Operational Rules

- Generated files should fail fast when required columns are missing.
- New schema fields must be added in the owning producer first, then documented here, then consumed by downstream code.
- If a stage cannot finish for one ECO, it should log the failure and continue with the remaining openings rather than aborting the whole pipeline.
