"""Lab 2 — prove the registered model can be reloaded by version, from the registry.

Usage:
    python scripts/reload_check.py --name itcs355-<studentid> --version 3

The model is downloaded from the Azure ML Model Registry by name and version.
No local training artifact is used.
"""
from __future__ import annotations

import argparse
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import joblib

from cloudlayer.factory import get_adapter
from src import config, data


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--name", required=True, help="registered model name")
    ap.add_argument("--version", required=True, help="registered model version")
    ap.add_argument("--rows", type=int, default=5)
    args = ap.parse_args()

    cfg = config.load(strict=False)
    adapter = get_adapter(cfg)
    client = adapter._ml_client()

    with tempfile.TemporaryDirectory(prefix="lab2_reload_") as tmp:
        download_dir = Path(tmp)

        print(
            f"loading Azure ML registry model "
            f"{args.name}:{args.version}"
        )

        client.models.download(
            name=args.name,
            version=args.version,
            download_path=str(download_dir),
        )

        candidates = list(download_dir.rglob("*.joblib"))

        if not candidates:
            raise FileNotFoundError(
                f"No .joblib model found after downloading "
                f"{args.name}:{args.version}"
            )

        model_path = candidates[0]
        print(f"downloaded artifact: {model_path}")

        model = joblib.load(model_path)

        df = data.load_raw(cfg.raw_path)
        _, _, test_df = data.split(df, seed=20260101)
        sample = test_df.head(args.rows)

        preds = model.predict_proba(sample[data.FEATURES])[:, 1]

        for rid, p in zip(sample[data.ID], preds):
            print(f"  reading {rid}: p(failure)={p:.4f}")

    print("\nPASS  model reloaded from the registry and scored rows")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())