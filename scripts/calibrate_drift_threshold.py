"""Lab 4 — choose the drift threshold from this pipeline's own noise.

A PSI threshold copied from a tutorial says nothing about YOUR feature volumes. This script
measures how large PSI gets when NOTHING has changed, then sets the threshold above that.

Method: generate fresh datasets from the same process with other seeds, take a window of
`--window` rows from each, and compute PSI against the reference for every feature. The
detector alerts when ANY feature crosses the threshold, so the relevant null statistic is
the MAXIMUM PSI across features in each trial. The threshold is the `--quantile` of that
maximum, rounded up to two decimals.

    python scripts/calibrate_drift_threshold.py --window 500 --trials 300
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from monitoring.drift import psi  # noqa: E402
from scripts.make_dataset import build  # noqa: E402
from src import data  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--reference", type=Path, default=ROOT / "data" / "raw" / "sensors.csv")
    ap.add_argument("--window", type=int, default=500)
    ap.add_argument("--trials", type=int, default=300)
    ap.add_argument("--quantile", type=float, default=0.99)
    ap.add_argument("--out", type=Path, default=ROOT / "monitoring" / "drift_threshold.json")
    args = ap.parse_args()

    reference = pd.read_csv(args.reference)
    ref = {f: reference[f].to_numpy(dtype=float) for f in data.FEATURES}

    maxima, per_feature = [], {f: [] for f in data.FEATURES}
    for trial in range(args.trials):
        fresh = build(seed=10_000 + trial).sample(n=args.window, random_state=trial)
        scores = {f: psi(ref[f], fresh[f].to_numpy(dtype=float)) for f in data.FEATURES}
        for f, v in scores.items():
            per_feature[f].append(v)
        maxima.append(max(scores.values()))

    q = float(np.quantile(maxima, args.quantile))
    threshold = math.ceil(q * 100) / 100
    result = {
        "window_rows": args.window,
        "trials": args.trials,
        "quantile": args.quantile,
        "null_max_psi_quantile": round(q, 5),
        "null_max_psi_median": round(float(np.median(maxima)), 5),
        "threshold": threshold,
        "per_feature_null_p99": {f: round(float(np.quantile(v, 0.99)), 5) for f, v in per_feature.items()},
        "conventional": {"no_change_below": 0.10, "significant_above": 0.25},
        "note": "threshold = ceil(quantile of max-over-features null PSI, 2 d.p.)",
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
