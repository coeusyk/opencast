"""Generate findings/findings.md and findings/findings.json using Gemini API."""

import json
import logging
import os
from datetime import datetime

import pandas as pd

_HERE = os.path.dirname(__file__)
FORECASTS_CSV = os.path.join(_HERE, "..", "data", "output", "forecasts.csv")
ENGINE_CSV    = os.path.join(_HERE, "..", "data", "output", "engine_delta.csv")
FINDINGS_DIR  = os.path.join(_HERE, "..", "findings")
OUTPUT_MD     = os.path.join(FINDINGS_DIR, "findings.md")
OUTPUT_JSON   = os.path.join(FINDINGS_DIR, "findings.json")

GEMINI_MODEL = "gemini-2.5-flash"

log = logging.getLogger(__name__)


# ── Gemini helpers ────────────────────────────────────────────────────────────

def _get_gemini_client():
    """Return a configured Gemini GenerativeModel, or None if API key is missing."""
    try:
        from dotenv import load_dotenv
        load_dotenv(os.path.join(_HERE, "..", ".env"))
        load_dotenv()
    except Exception:
        # Optional dependency in runtime environments that inject env directly.
        pass

    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        log.warning(
            "GEMINI_API_KEY is not set — skipping LLM analysis and using templated findings."
        )
        return None
    try:
        from google import genai
        return genai.Client(api_key=api_key)
    except Exception as exc:
        log.warning("Failed to initialise Gemini client: %s", exc)
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

def _forecast_directions(forecasts: pd.DataFrame) -> dict[str, str]:
    """Return {eco: 'rising'|'falling'|'stable'} based on last actual vs last forecast."""
    directions = {}
    for eco, grp in forecasts.groupby("eco"):
        grp = grp.sort_values("month")
        actual_rows  = grp[~grp["is_forecast"]]
        forecast_rows = grp[grp["is_forecast"]]
        if actual_rows.empty or forecast_rows.empty:
            directions[eco] = "stable"
            continue
        last_actual   = actual_rows["actual"].iloc[-1]
        last_forecast = forecast_rows["forecast"].iloc[-1]
        diff = last_forecast - last_actual
        if diff > 0.002:
            directions[eco] = "rising"
        elif diff < -0.002:
            directions[eco] = "falling"
        else:
            directions[eco] = "stable"
    return directions


def _steepest_trend(forecasts: pd.DataFrame) -> tuple[str, str, float]:
    """Return (eco, name, slope) for the opening with the steepest forecast trend."""
    best_eco: str = ""
    best_name: str = ""
    best_slope: float = 0.0
    for eco, grp in forecasts.groupby("eco"):
        grp = grp.sort_values("month")
        actual_rows   = grp[~grp["is_forecast"]]
        forecast_rows = grp[grp["is_forecast"]]
        if actual_rows.empty or forecast_rows.empty:
            continue
        slope = float(forecast_rows["forecast"].iloc[-1] - actual_rows["actual"].iloc[-1])
        if abs(slope) > abs(best_slope):
            best_slope = slope
            best_eco   = str(eco)
            best_name  = str(grp["opening_name"].iloc[0])
    return best_eco, best_name, best_slope


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

    directions = _forecast_directions(forecasts)

    # ── Summary statistics ───────────────────────────────────────────────────
    top_pos = delta_df.loc[delta_df["delta"].idxmax()]
    top_neg = delta_df.loc[delta_df["delta"].idxmin()]
    steep_eco, steep_name, steep_slope = _steepest_trend(forecasts)
    steep_dir = "rising" if steep_slope > 0 else "falling"

    summary = (
        f"Across the 20 tracked openings, **{top_pos['opening_name']} ({top_pos['eco']})** "
        f"shows the largest positive delta ({top_pos['delta']:+.4f}), meaning humans at "
        f"2000-rated blitz outperform Stockfish's win-probability prediction by the widest "
        f"margin. At the other extreme, **{top_neg['opening_name']} ({top_neg['eco']})** "
        f"has the largest negative delta ({top_neg['delta']:+.4f}), indicating it is the "
        f"most frequently misplayed or theory-dependent opening in the dataset. "
        f"The steepest ARIMA forecast trend belongs to **{steep_name} ({steep_eco})**, "
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
        f"*Generated using templated analysis (Gemini LLM call below).*",
    ]
    md_content = "\n".join(lines) + "\n"

    # ── Build data summaries for Gemini prompt ───────────────────────────────
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
        forecast_summary_rows.append({
            "eco": eco, "name": name,
            "last_actual": round(last_actual, 4),
            "last_forecast": round(last_fcast, 4),
            "direction": directions.get(str(eco), "stable"),
        })

    # ── Gemini structured JSON prompt ────────────────────────────────────────
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

    gemini_prompt = f"""You are a chess analytics expert. Analyse the data below and return ONLY a single valid JSON object matching the exact schema provided. No markdown fences, no preamble, no explanation — just the raw JSON.

Schema:
{json.dumps(schema_example, indent=2)}

Data:

Top 5 positive engine-human delta (humans outperform Stockfish prediction):
{top5_delta[['eco','opening_name','delta','interpretation']].to_string(index=False)}

Top 5 negative delta (humans underperform):
{bot5_delta[['eco','opening_name','delta','interpretation']].to_string(index=False)}

ARIMA forecast summary (last actual vs last forecast win rate):
{json.dumps(forecast_summary_rows, indent=2)}

Summary paragraph:
{summary}

Per-opening analysis (templated):
{chr(10).join(findings)}

Full report (findings.md):
{md_content}

Instructions:
- "generated_at" must be exactly "{today_str}"
- "month" must be exactly "{report_month}"
- "headline": the single most important finding from the data, 1-2 sentences
- panels.forecast.insight: 2-3 sentences specifically about the win-rate forecast trends
- panels.forecast.highlight_ecos: list of ECO codes worth highlighting in the forecast chart (2-4 codes)
- panels.engine_delta.insight: 2-3 sentences specifically about the engine-human delta patterns
- panels.engine_delta.outliers: list of ECO codes that are notable outliers (2-5 codes)
- panels.heatmap.insight: 2-3 sentences specifically about category-level win-rate patterns across time
- Return ONLY the JSON object. No markdown, no explanation."""

    gemini_client = _get_gemini_client()
    findings_json_data: dict | None = None

    if gemini_client is not None:
        try:
            from google.genai import types
            response = gemini_client.models.generate_content(
                model=GEMINI_MODEL,
                contents=gemini_prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                ),
            )
            
            if response.text is None:
                raise ValueError("Gemini returned empty response")
            
            raw_text = response.text.strip()

            # Strip markdown fences if the SDK didn't honour response_mime_type
            if raw_text.startswith("```"):
                raw_text = raw_text.split("\n", 1)[-1]
                if raw_text.endswith("```"):
                    raw_text = raw_text[: raw_text.rfind("```")]

            parsed = json.loads(raw_text)

            if _validate_findings_json(parsed):
                findings_json_data = parsed
                log.info("Gemini returned valid findings.json structure.")
            else:
                log.warning("Gemini response failed schema validation — using templated findings.json.")

        except Exception as exc:
            log.warning("Gemini call failed: %s — using templated findings.json.", exc)

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

    # ── Write findings.json ──────────────────────────────────────────────────
    if findings_json_data is not None:
        with open(OUTPUT_JSON, "w") as f:
            json.dump(findings_json_data, f, indent=2)
        print(f"findings.json written → {OUTPUT_JSON}")
    else:
        log.info("findings.json not written (Gemini unavailable or validation failed).")


# Keep the old name as an alias for backward compatibility
generate_report = run_report


if __name__ == "__main__":
    import logging as _logging
    _logging.basicConfig(level=_logging.INFO)
    run_report()

