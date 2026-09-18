"""Lab 2 Task 1 — submit the Lab 1 training container as a managed job.

    python scripts/train_remote.py --n-estimators 200 --max-depth 8 --seed 20260101

Thin wrapper around adapter.submit_training / wait_training so `make train-remote` has
something to call and so you get the same command whether you invoke it by hand or from
the Makefile.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cloudlayer.factory import get_adapter
from src import config


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n-estimators", type=int, default=200)
    ap.add_argument("--max-depth", type=int, default=8)
    ap.add_argument("--min-samples-leaf", type=int, default=5)
    ap.add_argument("--seed", type=int, default=20260101)
    args = ap.parse_args()

    cfg = config.load()
    adapter = get_adapter(cfg)

    image_uri_file = Path(".image_uri")
    if not image_uri_file.exists():
        raise SystemExit("No .image_uri found — run `make image-push` first.")
    image_uri = image_uri_file.read_text().strip()
    train_args = {
        "n-estimators": args.n_estimators,
        "max-depth": args.max_depth,
        "min-samples-leaf": args.min_samples_leaf,
        "seed": args.seed,
    }

    print(f"submitting job: image={image_uri} args={train_args}")
    job_id = adapter.submit_training(image_uri, train_args)
    print(f"submitted: {job_id}")

    print("waiting for completion (this polls every 15s)...")
    result = adapter.wait_training(job_id)
    print(f"done: {result}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())