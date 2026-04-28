import json
import os
import re

import pandas as pd

_HERE = os.path.dirname(__file__)
RAW_DIR = os.path.join(_HERE, "..", "data", "raw")
PROCESSED_DIR = os.path.join(_HERE, "..", "data", "processed")
OPENINGS_JSON = os.path.join(_HERE, "..", "openings.json")
OUTPUT_CSV = os.path.join(PROCESSED_DIR, "openings_ts.csv")

RATING_BRACKET = 2000
MIN_GAMES = 500
LOW_CONFIDENCE_THRESHOLD = 2000

_FNAME_RE = re.compile(r"^([A-E]\d{2})_(\d{4}-\d{2})\.json$")


def _load_name_map() -> dict:
    with open(OPENINGS_JSON) as f:
        openings = json.load(f)
    return {o["eco"]: o["name"] for o in openings}


def ingest() -> pd.DataFrame:
    name_map = _load_name_map()
    os.makedirs(PROCESSED_DIR, exist_ok=True)

    rows = []
    for fname in sorted(os.listdir(RAW_DIR)):
        m = _FNAME_RE.match(fname)
        if not m:
            continue
        eco, month = m.group(1), m.group(2)

        with open(os.path.join(RAW_DIR, fname)) as f:
            data = json.load(f)

        white = data["white"]
        draws = data["draws"]
        black = data["black"]
        total = white + draws + black

        if total < MIN_GAMES:
            continue

        rows.append({
            "month": month,
            "eco": eco,
            "opening_name": name_map.get(eco, eco),
            "rating_bracket": RATING_BRACKET,
            "white": white,
            "draws": draws,
            "black": black,
            "total": total,
            "white_win_rate": white / total,
            "low_confidence": total < LOW_CONFIDENCE_THRESHOLD,
        })

    df = pd.DataFrame(rows)
    df.to_csv(OUTPUT_CSV, index=False)
    print(f"Ingested {len(df)} rows → {OUTPUT_CSV}")
    return df


if __name__ == "__main__":
    ingest()
