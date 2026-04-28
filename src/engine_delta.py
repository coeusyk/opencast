import json
import math
import os

import chess
import pandas as pd
from stockfish import Stockfish

_HERE = os.path.dirname(__file__)
OPENINGS_JSON = os.path.join(_HERE, "..", "openings.json")
PROCESSED_CSV = os.path.join(_HERE, "..", "data", "processed", "openings_ts.csv")
OUTPUT_CSV    = os.path.join(_HERE, "..", "data", "output", "engine_delta.csv")
OUTPUT_DIR    = os.path.join(_HERE, "..", "data", "output")

STOCKFISH_PATH = "/usr/games/stockfish"
DEPTH = 20
HASH_MB = 256


def _get_fen_from_uci_moves(uci_moves: str) -> str:
    """Replay a comma-separated list of UCI moves and return the resulting FEN."""
    board = chess.Board()
    for uci in uci_moves.split(","):
        uci = uci.strip()
        if uci:
            board.push_uci(uci)
    return board.fen()


def _cp_to_prob(cp: int) -> float:
    """Standard sigmoid: P(white wins) = 1 / (1 + e^(-cp/400))"""
    return 1.0 / (1.0 + math.exp(-cp / 400.0))


def _interpret(delta: float) -> str:
    if delta > 0.04:
        return "humans outperform engine — rewards human skill"
    elif delta < -0.04:
        return "engine-favoured — frequently misplayed or theory-heavy"
    else:
        return "consistent with engine evaluation"


def run_engine_delta() -> pd.DataFrame:
    with open(OPENINGS_JSON) as f:
        openings = json.load(f)

    ts = pd.read_csv(PROCESSED_CSV)
    human_rates = (
        ts.groupby("eco")["white_win_rate"].mean().rename("human_win_rate_2000")
    )

    sf = Stockfish(
        path=STOCKFISH_PATH,
        depth=DEPTH,
        parameters={"Hash": HASH_MB, "Threads": 1},
    )

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    rows = []

    for opening in openings:
        eco   = opening["eco"]
        name  = opening["name"]
        moves = opening["moves"]

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

    df = pd.DataFrame(rows)
    df.to_csv(OUTPUT_CSV, index=False)
    print(f"\nEngine delta written → {OUTPUT_CSV}  ({len(df)} rows)")
    return df


if __name__ == "__main__":
    run_engine_delta()
