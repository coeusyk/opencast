import json
import logging
from pathlib import Path

import pandas as pd

_HERE = Path(__file__).resolve().parent
RAW_DIR = _HERE.parent / "data" / "raw"
OUTPUT_CSV = _HERE.parent / "data" / "output" / "move_stats.csv"

log = logging.getLogger(__name__)


def _require_months_dict(file_data: dict, fpath: Path) -> dict:
    months = file_data.get("months")
    if not isinstance(months, dict):
        log.warning("Skipping malformed raw file %s: missing months dict", fpath)
        return {}
    return months


def run_move_stats(raw_dir: Path = RAW_DIR, output_csv: Path = OUTPUT_CSV) -> pd.DataFrame:
    """Build per-move monthly stats used by Track 2 UX features.

    Output columns:
    eco, month, uci, san, games, white_win_rate, share_of_games,
    delta_share_12m, delta_wr_12m
    """
    rows: list[dict] = []

    for fpath in sorted(raw_dir.rglob("*.json")):
        try:
            with fpath.open(encoding="utf-8") as f:
                file_data = json.load(f)
        except Exception:
            log.warning("Skipping unreadable raw file %s", fpath)
            continue

        eco = str(file_data.get("eco", fpath.stem))
        months = _require_months_dict(file_data, fpath)
        if not months:
            continue

        for month, payload in sorted(months.items()):
            if not isinstance(payload, dict):
                log.warning("Skipping malformed move payload for %s %s", eco, month)
                continue

            month_white = int(payload.get("white", 0) or 0)
            month_draws = int(payload.get("draws", 0) or 0)
            month_black = int(payload.get("black", 0) or 0)
            month_total = month_white + month_draws + month_black
            if month_total <= 0:
                continue

            moves = payload.get("moves", [])
            if not isinstance(moves, list):
                log.warning("Skipping %s %s: moves payload is not a list", eco, month)
                continue

            for mv in moves:
                if not isinstance(mv, dict):
                    continue

                uci = str(mv.get("uci", "") or "").strip()
                san = str(mv.get("san", "") or "").strip()
                if not uci or not san:
                    continue

                white = int(mv.get("white", 0) or 0)
                draws = int(mv.get("draws", 0) or 0)
                black = int(mv.get("black", 0) or 0)
                games = white + draws + black
                if games <= 0:
                    continue

                rows.append(
                    {
                        "eco": eco,
                        "month": str(month),
                        "uci": uci,
                        "san": san,
                        "games": games,
                        "white_win_rate": white / games,
                        "share_of_games": games / month_total,
                    }
                )

    output_csv.parent.mkdir(parents=True, exist_ok=True)

    if not rows:
        empty = pd.DataFrame(
            columns=[
                "eco",
                "month",
                "uci",
                "san",
                "games",
                "white_win_rate",
                "share_of_games",
                "delta_share_12m",
                "delta_wr_12m",
            ]
        )
        empty.to_csv(output_csv, index=False)
        print(f"Move stats written -> {output_csv}  (0 rows)")
        return empty

    df = pd.DataFrame(rows)
    df["month_dt"] = pd.to_datetime(df["month"], format="%Y-%m", errors="coerce")
    df = df.dropna(subset=["month_dt"]).copy()

    df = df.sort_values(["eco", "uci", "month_dt"]).reset_index(drop=True)
    grp = df.groupby(["eco", "uci"], sort=False)
    df["delta_share_12m"] = df["share_of_games"] - grp["share_of_games"].shift(12)
    df["delta_wr_12m"] = df["white_win_rate"] - grp["white_win_rate"].shift(12)

    out = df[
        [
            "eco",
            "month",
            "uci",
            "san",
            "games",
            "white_win_rate",
            "share_of_games",
            "delta_share_12m",
            "delta_wr_12m",
        ]
    ].copy()
    out.to_csv(output_csv, index=False)
    print(f"Move stats written -> {output_csv}  ({len(out)} rows)")
    return out


if __name__ == "__main__":
    run_move_stats()
