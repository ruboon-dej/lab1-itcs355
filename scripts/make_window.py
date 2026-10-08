"""Lab 4 — take a window of recent rows, standing in for production inputs.

    python scripts/make_window.py --source data/fresh.csv --n 500 --out data/window.csv
"""
from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", type=Path, required=True)
    ap.add_argument("--n", type=int, default=500)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--out", type=Path, default=Path("data/window.csv"))
    args = ap.parse_args()
    df = pd.read_csv(args.source).sample(n=args.n, random_state=args.seed)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(args.out, index=False, lineterminator="\n")
    print(f"wrote {args.out}  rows={len(df)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
