"""Generate FINDINGS.md using Ollama LLM analysis with template fallback."""

import logging
import os
from datetime import datetime

import pandas as pd

_HERE = os.path.dirname(__file__)
FORECASTS_CSV = os.path.join(_HERE, "..", "data", "output", "forecasts.csv")
ENGINE_CSV    = os.path.join(_HERE, "..", "data", "output", "engine_delta.csv")
OUTPUT_MD     = os.path.join(_HERE, "..", "FINDINGS.md")

OLLAMA_HOST  = "http://localhost:11434"
OLLAMA_MODEL = "llama3.1:latest"

log = logging.getLogger(__name__)


# ── Ollama helpers ────────────────────────────────────────────────────────────

def _ollama_available() -> bool:
    """Return True if Ollama is reachable at OLLAMA_HOST."""
    try:
        import ollama
        ollama.Client(host=OLLAMA_HOST).list()
        return True
    except Exception:
        return False


def _llm_finding(eco: str, name: str, delta: float, interpretation: str,
                 trend: str, client) -> str:
    """Ask Ollama for a 2-sentence analyst finding about this opening."""
    prompt = (
        f"You are a chess analytics assistant. Write exactly 2 sentences about the "
        f"following opening based on the data provided. Be concise and analytical.\n\n"
        f"Opening: {name} ({eco})\n"
        f"Engine-human delta: {delta:+.4f} ({interpretation})\n"
        f"ARIMA win-rate trend: {trend}\n\n"
        f"Focus on what the delta and trend together reveal about how 2000-rated blitz "
        f"players handle this opening versus engine expectation."
    )
    try:
        import ollama
        response = client.chat(
            model=OLLAMA_MODEL,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.message.content.strip()
    except Exception as exc:
        log.warning("Ollama call failed for %s: %s", eco, exc)
        return _template_finding(eco, name, delta, interpretation, trend)


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
    use_llm = _ollama_available()
    if use_llm:
        import ollama
        client = ollama.Client(host=OLLAMA_HOST)
        log.info("Ollama reachable — generating LLM findings with %s", OLLAMA_MODEL)
    else:
        client = None
        log.warning(
            "Ollama not reachable at %s — falling back to templated findings", OLLAMA_HOST
        )

    findings: list[str] = []
    for _, row in delta_df.sort_values("delta", ascending=False).iterrows():
        eco   = row["eco"]
        name  = row["opening_name"]
        delta = float(row["delta"])
        interp = row["interpretation"]
        trend = directions.get(eco, "stable")

        if use_llm and client is not None:
            text = _llm_finding(eco, name, delta, interp, trend, client)
        else:
            text = _template_finding(eco, name, delta, interp, trend)

        findings.append(f"### {eco} — {name}\n\n{text}")

    # ── Write FINDINGS.md ────────────────────────────────────────────────────
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M UTC")
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
        f"*Generated {'with Ollama (' + OLLAMA_MODEL + ')' if use_llm else 'using templated analysis (Ollama unavailable)'}.*",
    ]

    content = "\n".join(lines) + "\n"
    os.makedirs(os.path.dirname(os.path.abspath(OUTPUT_MD)), exist_ok=True)
    with open(OUTPUT_MD, "w") as f:
        f.write(content)
    print(f"FINDINGS.md written → {OUTPUT_MD}  ({'LLM' if use_llm else 'template'})")


# Keep the old name as an alias for backward compatibility
generate_report = run_report


if __name__ == "__main__":
    import logging as _logging
    _logging.basicConfig(level=_logging.INFO)
    run_report()

