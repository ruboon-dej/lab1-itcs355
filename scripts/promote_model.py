"""Move a registered model version to another stage (a human decision, Lab 2 promotion policy).

    python scripts/promote_model.py --version 3 --stage production
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src import config  # noqa: E402,F401  (loads cloud.env)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--provider", default=os.environ.get("CLOUD_PROVIDER", "azure"))
    ap.add_argument("--model-name", default=os.environ.get("MODEL_REGISTRY_NAME"))
    ap.add_argument("--version", required=True)
    ap.add_argument("--stage", required=True, choices=["staging", "production", "archived"])
    args = ap.parse_args()
    from cloudlayer import registry

    registry.promote(args.provider, args.model_name, args.version, args.stage)
    print(f"{args.model_name}:{args.version} -> stage={args.stage}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
