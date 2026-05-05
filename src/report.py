"""Generate findings/findings.md and findings/findings.json using Groq API (llama-3.1-8b-instant)."""

import json
import logging
import os
import time
from datetime import datetime

import pandas as pd

_HERE = os.path.dirname(__file__)
FORECASTS_CSV = os.path.join(_HERE, "..", "data", "output", "forecasts.csv")
ENGINE_CSV    = os.path.join(_HERE, "..", "data", "output", "engine_delta.csv")
FINDINGS_DIR  = os.path.join(_HERE, "..", "findings")
OUTPUT_MD     = os.path.join(FINDINGS_DIR, "findings.md")
OUTPUT_JSON   = os.path.join(FINDINGS_DIR, "findings.json")
NARRATIVES_JSON = os.path.join(FINDINGS_DIR, "narratives.json")
CATALOG_CSV   = os.path.join(_HERE, "..", "data", "openings_catalog.csv")

GROQ_MODEL = "llama-3.1-8b-instant"
NARRATIVE_BATCH_SIZE = 8    # openings per Groq call (respects 6K TPM limit)
NARRATIVE_BATCH_SLEEP = 22  # seconds between narrative batches
MAX_NARRATIVE_OPENINGS = 100

log = logging.getLogger(__name__)


# ── Groq helpers ─────────────────────────────────────────────────────────────

def _get_groq_client():
    """Return a configured Groq client, or None if API key is missing."""
    try:
        from dotenv import load_dotenv
        load_dotenv(os.path.join(_HERE, "..", ".env"))
        load_dotenv()
    except Exception:
        pass

    api_key = os.environ.get("GROQ_API_KEY", "").strip()
    if not api_key:
        log.warning(
            "GROQ_API_KEY is not set — skipping LLM analysis and using templated findings."
        )
        return None
    try:
        from groq import Groq
        return Groq(api_key=api_key)
    except Exception as exc:
        log.warning("Failed to initialise Groq client: %s", exc)
        return None


def _groq_call(client, prompt: str, max_tokens: int = 1500) -> str | None:
    """Call Groq with retry on rate-limit errors. Returns raw JSON string or None."""
    for attempt in range(3):
        try:
            response = client.chat.completions.create(
                model=GROQ_MODEL,
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
                max_tokens=max_tokens,
                temperature=0.3,
            )
            return response.choices[0].message.content
        except Exception as exc:
            err = str(exc)
            if "429" in err or "rate_limit" in err.lower():
                wait = 60 * (attempt + 1)
                log.warning("Groq rate limited; waiting %ds before retry %d/3.", wait, attempt + 1)
                time.sleep(wait)
            else:
                log.warning("Groq call failed (attempt %d/3): %s", attempt + 1, exc)
                if attempt == 2:
                    return None
                time.sleep(5)
    return None


def _template_finding(eco: str, name: str, delta: float, interpretation: str,
                      trend: str) -> str:
    """Fallback 2-sentence templated finding."""
    direction = "above" if delta > 0 else "below"
    magnitude = "notably" if abs(delta) > 0.04 else "slightly"
    return (
        f"The {name} ({eco}) shows a human win rate that is {magnitude} {direction} "
        f"Stockfish's prediction by {abs(delta):.4f} — {interpretation}. "
        f"The ARIMA model projects a {trend} trend over the next three months."
    )


# ── JSON schema validation ────────────────────────────────────────────────────

_REQUIRED_KEYS = {"generated_at", "month", "headline", "panels"}
_REQUIRED_PANELS = {"forecast", "engine_delta", "heatmap"}


def _validate_findings_json(data: dict) -> bool:
    """Return True if *data* matches the required findings.json schema."""
    if not isinstance(data, dict):
        return False
    if not _REQUIRED_KEYS.issubset(data.keys()):
        log.warning("findings.json missing keys: %s", _REQUIRED_KEYS - data.keys())
        return False
    panels = data.get("panels", {})
    if not isinstance(panels, dict) or not _REQUIRED_PANELS.issubset(panels.keys()):
        log.warning("findings.json panels missing: %s", _REQUIRED_PANELS - panels.keys())
        return False
    for panel_name in _REQUIRED_PANELS:
        if "insight" not in panels.get(panel_name, {}):
            log.warning("findings.json panel '%s' missing 'insight'", panel_name)
            return False
    return True


def _build_templated_findings_json(
    *,
    report_date: str,
    report_month: str,
    delta_df: pd.DataFrame,
    directions: dict[str, str],
) -> dict:
    """Build deterministic findings.json content when Gemini is unavailable."""
    top_pos = delta_df.loc[delta_df["delta"].idxmax()]
    top_neg = delta_df.loc[delta_df["delta"].idxmin()]

    rising = [eco for eco, trend in directions.items() if trend == "rising"]
    falling = [eco for eco, trend in directions.items() if trend == "falling"]

    outliers = (
        delta_df.iloc[delta_df["delta"].abs().sort_values(ascending=False).index]
        .head(4)["eco"]
        .astype(str)
        .tolist()
    )

    highlight_ecos = []
    highlight_ecos.extend(rising[:2])
    highlight_ecos.extend(falling[:2])
    if not highlight_ecos:
        highlight_ecos = delta_df.head(2)["eco"].astype(str).tolist()

    data = {
        "generated_at": report_date,
        "month": report_month,
        "headline": (
            f"{top_pos['opening_name']} ({top_pos['eco']}) shows the strongest positive human-vs-engine "
            f"gap, while {top_neg['opening_name']} ({top_neg['eco']}) remains the largest negative outlier."
        ),
        "panels": {
            "forecast": {
                "insight": (
                    f"Forecast directions suggest mixed momentum across openings, with {len(rising)} rising and "
                    f"{len(falling)} falling trajectories in the next horizon. The strongest signals are best read "
                    "alongside uncertainty bands to separate stable trends from short-term noise."
                ),
                "highlight_ecos": list(dict.fromkeys(highlight_ecos))[:4],
            },
            "engine_delta": {
                "insight": (
                    f"Engine-human deltas remain asymmetric: {top_pos['eco']} leads positive outperformance, "
                    f"while {top_neg['eco']} underperforms most against engine expectation. These outliers "
                    "flag openings where practical play diverges most from theoretical evaluation."
                ),
                "outliers": outliers,
            },
            "heatmap": {
                "insight": (
                    "Category-level heatmap patterns continue to show non-uniform performance over time, with "
                    "month-to-month variation indicating shifting practical preferences across ECO families."
                ),
            },
        },
    }
    return data


# ── Forecast direction ────────────────────────────────────────────────────────

def _forecast_directions(
    forecasts: pd.DataFrame,
) -> tuple[dict[str, str], dict]:
    """Return (directions, signals) using OLS regression over the actual series.

    *directions* maps eco -> 'rising'|'falling'|'stable'.
    *signals* maps eco -> TrendSignal (for narrative enrichment).
    The structural_break column in *forecasts* is passed to the classifier so
    that a recent regime change causes only post-break data to be used.
    """
    from .trend_classifier import classify_trend, TrendSignal

    directions: dict[str, str] = {}
    signals: dict[str, TrendSignal] = {}

    for eco, grp in forecasts.groupby("eco"):
        eco = str(eco)  # Convert Scalar to str for dictionary keys
        grp = grp.sort_values("month")
        actual_rows = grp[~grp["is_forecast"]]
        if actual_rows.empty:
            directions[eco] = "stable"
            continue

        breaks = (
            actual_rows["structural_break"].reset_index(drop=True)
            if "structural_break" in actual_rows.columns
            else None
        )
        signal = classify_trend(
            eco,
            actual_rows["actual"].reset_index(drop=True),
            structural_breaks=breaks,
        )
        directions[eco] = signal.direction
        signals[eco] = signal

    return directions, signals


def _full_series_ols(
    forecasts: pd.DataFrame,
) -> list[tuple[str, str, float, float]]:
    """Compute OLS on full actuals (no break truncation) matching the JS chart logic.

    Returns list of (eco, direction, slope, r_squared) sorted by slope descending.
    """
    import numpy as np
    from scipy import stats as _stats

    _SLOPE_THRESHOLD = 0.0003
    _MIN_R2 = 0.15
    results: list[tuple[str, str, float, float]] = []
    
    for eco, grp in forecasts.groupby("eco"):
        grp = grp.sort_values("month")
        actuals = grp[~grp["is_forecast"]]["actual"].dropna().values.astype(float)
        if len(actuals) < 6:
            continue

        x = np.arange(len(actuals), dtype=float)
        reg_result = _stats.linregress(x, actuals)  # type: ignore
        slope = float(reg_result[0])  # type: ignore
        r_value = float(reg_result[2])  # type: ignore
        r_sq = r_value ** 2

        if abs(slope) < _SLOPE_THRESHOLD or r_sq < _MIN_R2:
            direction = "stable"
        elif slope > 0:
            direction = "rising"
        else:
            direction = "falling"

        results.append((str(eco), direction, slope, r_sq))

    results.sort(key=lambda t: -t[2])
    return results


def _steepest_trend(
    forecasts: pd.DataFrame,
    signals: dict,
) -> tuple[str, str, float]:
    """Return (eco, name, slope) for the opening with the steepest full-series OLS trend."""
    best_eco: str = ""
    best_name: str = ""
    best_slope: float = 0.0

    for eco, direction, slope, r_sq in _full_series_ols(forecasts):
        if direction == "stable":
            continue
        if abs(slope) > abs(best_slope):
            best_slope = slope
            best_eco = eco
            grp = forecasts[forecasts["eco"] == eco]
            name_candidate = str(grp["opening_name"].iloc[0]).strip() if not grp.empty else ""
            if not name_candidate or name_candidate == eco:
                try:
                    cat = pd.read_csv(CATALOG_CSV)
                    cat_row = cat[cat["eco"] == eco]
                    name_candidate = str(cat_row["name"].iloc[0]) if not cat_row.empty else ""
                except Exception:
                    name_candidate = ""
            best_name = name_candidate

    return best_eco, best_name, best_slope


def _load_narratives_json() -> dict:
    """Load existing narratives.json or return an empty structure."""
    try:
        with open(NARRATIVES_JSON, encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict) or "per_opening" not in data:
            return {"per_opening": {}}
        return data
    except Exception:
        return {"per_opening": {}}


# ── Main ──────────────────────────────────────────────────────────────────────

def run_report() -> None:
    forecasts = pd.read_csv(
        FORECASTS_CSV,
        converters={
            "structural_break": lambda value: str(value).strip().lower() == "true",
            "is_forecast": lambda v: str(v).strip().lower() == "true",
        },
    )
    delta_df  = pd.read_csv(ENGINE_CSV)

    directions, signals = _forecast_directions(forecasts)

    # ── Summary statistics ───────────────────────────────────────────────────
    top_pos = delta_df.loc[delta_df["delta"].idxmax()]
    top_neg = delta_df.loc[delta_df["delta"].idxmin()]
    steep_eco, steep_name, steep_slope = _steepest_trend(forecasts, signals)
    steep_dir = "rising" if steep_slope > 0 else "falling"

    summary = (
        f"Across the 20 tracked openings, **{top_pos['opening_name']} ({top_pos['eco']})** "
        f"shows the largest positive delta ({top_pos['delta']:+.4f}), meaning humans at "
        f"2000-rated blitz outperform Stockfish's win-probability prediction by the widest "
        f"margin. At the other extreme, **{top_neg['opening_name']} ({top_neg['eco']})** "
        f"has the largest negative delta ({top_neg['delta']:+.4f}), indicating it is the "
        f"most frequently misplayed or theory-dependent opening in the dataset. "
        f"The steepest ARIMA forecast trend belongs to **{steep_name + ' ' if steep_name and steep_name != steep_eco else ''}({steep_eco})**, "
        f"whose win rate is projected to be {steep_dir} most sharply over the next three months."
    )

    # ── Per-opening findings ─────────────────────────────────────────────────
    findings: list[str] = []
    for _, row in delta_df.sort_values("delta", ascending=False).iterrows():
        eco   = row["eco"]
        name  = row["opening_name"]
        delta = float(row["delta"])
        interp = row["interpretation"]
        trend = directions.get(eco, "stable")
        text = _template_finding(eco, name, delta, interp, trend)
        findings.append(f"### {eco} — {name}\n\n{text}")

    # ── Build FINDINGS.md content ────────────────────────────────────────────
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M UTC")
    report_month = datetime.now().strftime("%Y-%m")
    lines = [
        f"# OpenCast Findings",
        f"",
        f"*Last updated: {timestamp}*",
        f"",
        f"---",
        f"",
        f"## Summary",
        f"",
        summary,
        f"",
        f"---",
        f"",
        f"## Per-Opening Analysis",
        f"",
        *findings,
        f"",
        f"---",
        f"",
        f"*Generated using templated analysis (Groq LLM call below).*",
    ]
    md_content = "\n".join(lines) + "\n"

    # ── Build data summaries for Groq prompt ───────────────────────────────
    top5_delta = delta_df.sort_values("delta", ascending=False).head(5)
    bot5_delta = delta_df.sort_values("delta").head(5)

    forecast_summary_rows = []
    for eco, grp in forecasts.groupby("eco"):
        actual_rows = grp[~grp["is_forecast"]]
        fcast_rows = grp[grp["is_forecast"]]
        if actual_rows.empty or fcast_rows.empty:
            continue
        last_actual = float(actual_rows["actual"].iloc[-1])
        last_fcast = float(fcast_rows["forecast"].iloc[-1])
        name = str(grp["opening_name"].iloc[0])
        sig = signals.get(str(eco))
        forecast_summary_rows.append({
            "eco": eco,
            "name": name,
            "last_actual": round(last_actual, 4),
            "last_forecast": round(last_fcast, 4),
            "direction": directions.get(str(eco), "stable"),
            "trend_slope_per_month": round(sig.slope_per_month, 6) if sig else 0.0,
            "trend_r_squared": round(sig.r_squared, 4) if sig else 0.0,
            "trend_confidence": sig.confidence if sig else "low",
            "recent_volatility": round(sig.recent_volatility, 6) if sig else 0.0,
            "sustained_streak_months": sig.sustained_months if sig else 0,
        })

    # ── Groq structured JSON prompt ──────────────────────────────────────────
    today_str = datetime.now().strftime("%Y-%m-%d")
    schema_example = {
        "generated_at": today_str,
        "month": report_month,
        "headline": "<single most important finding, 1-2 sentences>",
        "panels": {
            "forecast": {
                "insight": "<2-3 sentences directly about the win-rate forecast chart>",
                "highlight_ecos": ["ECO1", "ECO2"],
            },
            "engine_delta": {
                "insight": "<2-3 sentences directly about the engine-human delta chart>",
                "outliers": ["ECO1", "ECO2", "ECO3"],
            },
            "heatmap": {
                "insight": "<2-3 sentences directly about the ECO category heatmap>",
            },
        },
    }

    # Load existing narratives for incremental merge
    existing_narratives = _load_narratives_json()
    new_per_opening: dict[str, str] = {}

    groq_client = _get_groq_client()
    findings_json_data: dict | None = None

    if groq_client is not None:
        # ── Call 1: main findings.json (condensed prompt, no per_opening) ────
        findings_schema = dict(schema_example)  # no per_opening key
        groq_findings_prompt = f"""You are a chess analytics expert. Return ONLY a valid JSON object matching the schema. No markdown, no explanation.

Schema:
{json.dumps(findings_schema, indent=2)}

Top 5 positive engine-human delta (humans outperform Stockfish):
{top5_delta[['eco','opening_name','delta','interpretation']].to_string(index=False)}

Top 5 negative delta (humans underperform):
{bot5_delta[['eco','opening_name','delta','interpretation']].to_string(index=False)}

ARIMA forecast directions ({len(forecast_summary_rows)} openings, sample):
{json.dumps(forecast_summary_rows[:15], indent=2)}

Summary: {summary}

Instructions:
- generated_at must be "{today_str}"
- month must be "{report_month}"
- headline: 1-2 sentences, single most important finding
- panels.forecast.insight: 2-3 sentences about win-rate forecast trends
- panels.forecast.highlight_ecos: 2-4 ECO codes worth highlighting
- panels.engine_delta.insight: 2-3 sentences about engine-human delta patterns
- panels.engine_delta.outliers: 2-5 notable outlier ECO codes
- panels.heatmap.insight: 2-3 sentences about category-level patterns
- Return ONLY the JSON object."""

        try:
            raw_text = _groq_call(groq_client, groq_findings_prompt, max_tokens=700)
            if raw_text is None:
                raise ValueError("Groq returned no text for findings.json")
            parsed = json.loads(raw_text.strip())
            parsed.pop("per_opening", None)
            if _validate_findings_json(parsed):
                findings_json_data = parsed
                log.info("Groq returned valid findings.json structure.")
            else:
                log.warning("Groq findings.json failed schema validation — using templated fallback.")
        except Exception as exc:
            log.warning("Groq findings call failed: %s — using templated findings.json.", exc)

        # ── Calls 2+: per-opening narratives in batches ───────────────────────
        # Sort by |delta| descending so the most interesting openings get narratives first.
        delta_lookup = {
            str(row["eco"]): (float(row["delta"]), str(row["interpretation"]))
            for _, row in delta_df.iterrows()
        }
        # Filter out openings with no usable data before spending Groq tokens.
        try:
            _catalog_df = pd.read_csv(CATALOG_CSV)
            _ok_ecos = set(
                _catalog_df.loc[
                    _catalog_df.get("data_status", pd.Series(["ok"] * len(_catalog_df))) == "ok",
                    "eco",
                ].astype(str).tolist()
            ) if "data_status" in _catalog_df.columns else None
        except Exception:
            _ok_ecos = None  # if catalog unavailable, don't filter

        _eligible = (
            [r for r in forecast_summary_rows if str(r["eco"]) in _ok_ecos]
            if _ok_ecos is not None
            else forecast_summary_rows
        )

        # Sort candidates: ECOs without existing narratives first (priority), then by |delta|.
        existing_eco_set = set(existing_narratives.get("per_opening", {}).keys())
        narrative_candidates = sorted(
            _eligible,
            key=lambda r: (
                1 if str(r["eco"]) in existing_eco_set else 0,  # 0 = no narrative (higher priority)
                -abs(delta_lookup.get(str(r["eco"]), (0,))[0]),
            ),
        )[:MAX_NARRATIVE_OPENINGS]

        narrative_schema_ex = {
            "<ECO1>": "<2-3 sentences covering trend direction, engine delta, and what it means for the player. Under 60 words.>",
            "<ECO2>": "<narrative...>",
        }

        for batch_start in range(0, len(narrative_candidates), NARRATIVE_BATCH_SIZE):
            batch = narrative_candidates[batch_start: batch_start + NARRATIVE_BATCH_SIZE]
            batch_data = [
                {
                    **r,
                    "delta": delta_lookup.get(str(r["eco"]), (0.0,))[0],
                    "interpretation": delta_lookup.get(str(r["eco"]), (0.0, "n/a"))[1],
                }
                for r in batch
            ]
            narrative_prompt = f"""You are a chess analytics expert. Return ONLY a valid JSON object where each key is an ECO code and the value is a 2-3 sentence narrative (under 60 words each). No markdown, no explanation.

Schema example:
{json.dumps(narrative_schema_ex, indent=2)}

Openings to analyse:
{json.dumps(batch_data, indent=2)}

RULES — apply to every opening, in order:

1. TREND LANGUAGE (based on trend_confidence + direction):
    - trend_confidence = "high" AND sustained_streak_months >= 3: assert direction firmly — "has been rising/falling consistently"
    - trend_confidence = "medium" OR sustained_streak_months in [1, 2]: hedge — "shows signs of rising/falling" or "has trended upward/downward recently"
    - trend_confidence = "low" OR direction = "stable": never use "rising"/"falling" — use "erratic", "range-bound", or "showing no clear trend"

2. DELTA COHERENCE (engine-human gap):
    - delta > 0: humans outperform engine prediction → practical play favours white
    - delta < 0: humans underperform engine prediction → white's theoretical advantage is not being realised in play
    - |delta| > 0.04: describe as a "major gap"
    - |delta| 0.02–0.04: describe as a "notable gap"
    - |delta| < 0.02: describe as a "minor gap"
    - CRITICAL: never write that a trend is "rising" and simultaneously imply delta is negative without acknowledging the contradiction. If direction says "rising" but delta is negative, the win rate trend and the engine gap are telling different stories — say so.

3. VOLATILITY (recent_volatility = std dev of last 6 months of win-rate):
    - recent_volatility > 0.005: mention the series is "noisy" or "highly variable month-to-month"
    - recent_volatility 0.002–0.005: optionally note "moderate variability"
    - recent_volatility < 0.002: do not mention volatility

4. PLAYER RECOMMENDATION:
    - End each narrative with one concrete implication for a 2000-rated player: should they adopt, avoid, or monitor this opening?
    - Base the recommendation on the direction+confidence combination and the delta sign — not just delta magnitude alone.

5. FORMAT:
    - Under 60 words per narrative.
    - No bullet points. Flowing prose only.
    - Do not start with the ECO code or the opening name — begin with the insight.
    - Return ONLY the JSON object."""
            try:
                raw = _groq_call(groq_client, narrative_prompt, max_tokens=600)
                if raw:
                    parsed_narratives = json.loads(raw.strip())
                    for eco_key, narrative in parsed_narratives.items():
                        if isinstance(narrative, str) and narrative.strip():
                            new_per_opening[eco_key] = narrative.strip()
                    log.info(
                        "Groq narrative batch %d/%d: %d ECOs returned.",
                        batch_start // NARRATIVE_BATCH_SIZE + 1,
                        -(-len(narrative_candidates) // NARRATIVE_BATCH_SIZE),
                        len(parsed_narratives),
                    )
            except Exception as exc:
                log.warning("Groq narrative batch failed: %s", exc)

            # Respect 6K TPM: sleep between batches (skip after last batch)
            if batch_start + NARRATIVE_BATCH_SIZE < len(narrative_candidates):
                log.info("Sleeping %ds between Groq narrative batches (TPM limit).", NARRATIVE_BATCH_SLEEP)
                time.sleep(NARRATIVE_BATCH_SLEEP)

    if findings_json_data is None:
        findings_json_data = _build_templated_findings_json(
            report_date=today_str,
            report_month=report_month,
            delta_df=delta_df,
            directions=directions,
        )
        if not _validate_findings_json(findings_json_data):
            log.warning("Templated findings.json failed validation — skipping JSON write.")
            findings_json_data = None

    # ── Write findings.md ────────────────────────────────────────────────────
    os.makedirs(FINDINGS_DIR, exist_ok=True)
    with open(OUTPUT_MD, "w") as f:
        f.write(md_content)
    print(f"findings.md written → {OUTPUT_MD}")

    # ── Write findings.json (no per_opening key) ─────────────────────────────
    if findings_json_data is not None:
        with open(OUTPUT_JSON, "w") as f:
            json.dump(findings_json_data, f, indent=2)
        print(f"findings.json written → {OUTPUT_JSON}")
    else:
        log.info("findings.json not written (Groq unavailable or validation failed).")

    # ── Write narratives.json (incremental merge) ─────────────────────────────
    if new_per_opening:
        merged_per_opening = existing_narratives.get("per_opening", {}).copy()
        merged_per_opening.update(new_per_opening)  # new overrides old for same ECOs
        narratives_out = {
            "generated_at": today_str,
            "per_opening": merged_per_opening,
        }
        with open(NARRATIVES_JSON, "w", encoding="utf-8") as f:
            json.dump(narratives_out, f, indent=2, ensure_ascii=False)
        print(f"narratives.json written → {NARRATIVES_JSON}  ({len(merged_per_opening)} ECOs)")
    else:
        log.info("No per-opening narratives generated — narratives.json unchanged.")


# Keep the old name as an alias for backward compatibility
generate_report = run_report


if __name__ == "__main__":
    import logging as _logging
    _logging.basicConfig(level=_logging.INFO)
    run_report()

