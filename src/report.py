"""Auto-generate FINDINGS.md from pipeline output CSVs."""

import os
from datetime import date

import pandas as pd

_HERE = os.path.dirname(__file__)
FORECASTS_CSV  = os.path.join(_HERE, "..", "data", "output", "forecasts.csv")
ENGINE_CSV     = os.path.join(_HERE, "..", "data", "output", "engine_delta.csv")
OUTPUT_MD      = os.path.join(_HERE, "..", "FINDINGS.md")


def _fmt_table(df: pd.DataFrame, columns: list[str], headers: list[str]) -> str:
    rows = [" | ".join(headers), " | ".join(["---"] * len(headers))]
    for _, row in df[columns].iterrows():
        rows.append(" | ".join(str(row[c]) for c in columns))
    return "\n".join(rows)


def generate_report() -> None:
    forecasts = pd.read_csv(
        FORECASTS_CSV,
        converters={
            "structural_break": lambda value: str(value).strip().lower() == "true"
        },
    )
    delta     = pd.read_csv(ENGINE_CSV)

    # ── Structural breaks ───────────────────────────────────────────────────
    breaks = forecasts[forecasts["structural_break"]]
    break_counts = (
        breaks.groupby("eco")["month"]
        .count()
        .rename("break_count")
        .sort_values(ascending=False)
        .reset_index()
    )
    total_breaks = len(breaks)

    # ── Engine delta top / bottom ───────────────────────────────────────────
    top_human  = delta.sort_values("delta", ascending=False).head(5)
    top_engine = delta.sort_values("delta", ascending=True).head(5)

    # ── Most misplayed (large negative delta = engine likes it, humans don't) ─
    misplayed = delta[delta["delta"] < 0].sort_values("delta").head(5)

    today = date.today().strftime("%Y-%m-%d")

    lines = [
        f"# OpenCast Findings",
        f"",
        f"*Auto-generated on {today} from pipeline outputs.*",
        f"",
        f"---",
        f"",
        f"## Structural Breaks",
        f"",
        f"**{total_breaks} structural breaks** detected across {len(break_counts)} openings.",
        f"",
        _fmt_table(
            break_counts,
            ["eco", "break_count"],
            ["ECO", "Breaks"],
        ),
        f"",
        f"---",
        f"",
        f"## Engine Delta",
        f"",
        f"### Most Human-Favourable (positive delta — humans outperform engine prediction)",
        f"",
        _fmt_table(
            top_human,
            ["eco", "opening_name", "engine_cp", "human_win_rate_2000", "delta"],
            ["ECO", "Opening", "Engine cp", "Human WR", "Delta"],
        ),
        f"",
        f"### Most Engine-Favourable (negative delta — engine beats human play)",
        f"",
        _fmt_table(
            top_engine,
            ["eco", "opening_name", "engine_cp", "human_win_rate_2000", "delta"],
            ["ECO", "Opening", "Engine cp", "Human WR", "Delta"],
        ),
        f"",
        f"---",
        f"",
        f"## Most Misplayed Openings",
        f"",
        f"Openings where humans consistently underperform the engine's win-probability prediction:",
        f"",
    ]

    if misplayed.empty:
        lines.append("*None — humans outperform the engine in all tracked openings.*")
    else:
        lines.append(
            _fmt_table(
                misplayed,
                ["eco", "opening_name", "delta", "interpretation"],
                ["ECO", "Opening", "Delta", "Assessment"],
            )
        )

    content = "\n".join(lines) + "\n"
    with open(OUTPUT_MD, "w") as f:
        f.write(content)
    print(f"FINDINGS.md written → {OUTPUT_MD}")


if __name__ == "__main__":
    generate_report()
