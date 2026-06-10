import logging
import math
import os
import shutil
import time

import chess
import pandas as pd
from stockfish import Stockfish

_HERE = os.path.dirname(__file__)
PROCESSED_CSV = os.path.join(_HERE, "..", "data", "processed", "openings_ts.csv")
CATALOG_CSV   = os.path.join(_HERE, "..", "data", "openings_catalog.csv")
OUTPUT_CSV    = os.path.join(_HERE, "..", "data", "output", "engine_delta.csv")
OUTPUT_DIR    = os.path.join(_HERE, "..", "data", "output")

STOCKFISH_PATH = shutil.which("stockfish") or "/usr/games/stockfish"
DEPTH = 20
HASH_MB = 256
ENGINE_TOTAL_WARN_S = 300.0  # warn if total evaluation exceeds 5 min

log = logging.getLogger(__name__)

REQUIRED_CATALOG_COLUMNS = {"eco", "name", "moves", "model_tier"}
REQUIRED_TS_COLUMNS = {"eco", "white_win_rate"}


def _require_columns(df: pd.DataFrame, required: set[str], source: str) -> None:
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"{source} missing required columns: {sorted(missing)}")


def _get_fen_from_uci_moves(uci_moves: str) -> str:
    """Replay UCI moves and return the resulting FEN.

    Accept any non-empty move sequence from the catalog so short opening definitions
    (for example one or two plies) are still evaluated instead of being dropped.
    """
    board = chess.Board()
    move_list = [uci.strip() for uci in uci_moves.split(",") if uci.strip()]
    if not move_list:
        raise ValueError(f"Move sequence is empty: {uci_moves!r}")
    for uci in move_list:
        board.push_uci(uci)
    return board.fen()


def _cp_to_prob(cp: int) -> float:
    """Standard sigmoid: P(white wins) = 1 / (1 + e^(-cp/400))"""
    return 1.0 / (1.0 + math.exp(-cp / 400.0))


def _interpret(delta: float) -> str:
    if delta > 0.04:
        return "humans outperform engine \u2014 rewards human skill"
    elif delta < -0.04:
        return "engine-favoured \u2014 frequently misplayed or theory-heavy"
    else:
        return "consistent with engine evaluation"


def run_engine_delta() -> pd.DataFrame:
    # Load Tier-1 openings directly from the catalogue (single source of truth)
    catalog = pd.read_csv(CATALOG_CSV)
    _require_columns(catalog, REQUIRED_CATALOG_COLUMNS, CATALOG_CSV)
    tier1 = catalog[catalog["model_tier"] == 1][["eco", "name", "moves"]].copy()
    tier1 = tier1.dropna(subset=["moves"])
    openings = tier1.to_dict("records")
    log.info("Engine delta: evaluating %d Tier-1 ECOs", len(openings))

    ts = pd.read_csv(PROCESSED_CSV)
    _require_columns(ts, REQUIRED_TS_COLUMNS, PROCESSED_CSV)
    human_rates = (
        ts.groupby("eco")["white_win_rate"].mean().rename("human_win_rate_2000")
    )

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    rows = []

    sf = Stockfish(
        path=STOCKFISH_PATH,
        depth=DEPTH,
        parameters={"Hash": HASH_MB, "Threads": 1},
    )
    t_start = time.perf_counter()
    try:
        for opening in openings:
            eco   = opening["eco"]
            name  = opening["name"]
            moves = opening["moves"]

            try:
                fen = _get_fen_from_uci_moves(moves)
                sf.set_fen_position(fen)
                evaluation = sf.get_evaluation()

                if evaluation["type"] == "cp":
                    cp = int(evaluation["value"])
                else:  # mate
                    mate_in = int(evaluation["value"])
                    cp = 10000 if mate_in > 0 else -10000

                p_engine = _cp_to_prob(cp)
                human_rate = float(human_rates.get(eco, float("nan")))
                if not math.isfinite(human_rate):
                    log.warning("Skipping %s (%s): missing human win rate", eco, name)
                    continue
                delta = human_rate - p_engine

                print(f"{eco:4s} {name:30s}  cp={cp:+5d}  P_engine={p_engine:.4f}  "
                      f"human={human_rate:.4f}  delta={delta:+.4f}")

                rows.append({
                    "eco": eco,
                    "opening_name": name,
                    "engine_cp": cp,
                    "p_engine": round(p_engine, 6),
                    "human_win_rate_2000": round(human_rate, 6),
                    "delta": round(delta, 6),
                    "interpretation": _interpret(delta),
                })
            except Exception as exc:
                log.warning("Skipping %s (%s): %s", eco, name, exc)
                continue
    finally:
        del sf

    total_elapsed = time.perf_counter() - t_start
    log.info("Engine delta: completed in %.1fs", total_elapsed)
    if total_elapsed > ENGINE_TOTAL_WARN_S:
        log.warning(
            "WARNING: engine_delta total time %.1fs exceeded 5 min budget",
            total_elapsed,
        )

    df = pd.DataFrame(rows)
    df.to_csv(OUTPUT_CSV, index=False)
    print(f"\nEngine delta written \u2192 {OUTPUT_CSV}  ({len(df)} rows)")
    return df


def recommend_openings(delta_df: pd.DataFrame | None = None) -> pd.DataFrame:
    """Return openings ranked by delta (highest = most human-favourable)."""
    if delta_df is None:
        delta_df = pd.read_csv(OUTPUT_CSV)
    return (
        delta_df[["eco", "opening_name", "engine_cp", "p_engine",
                  "human_win_rate_2000", "delta", "interpretation"]]
        .sort_values("delta", ascending=False)
        .reset_index(drop=True)
    )


if __name__ == "__main__":
    run_engine_delta()
