"""Register the candidate model with lineage tags. Runs only behind the gate.

Defence in depth: even though the pipeline only starts this step when the gate says go,
the script re-reads decision.json and refuses to register a rejected candidate.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--provider", default=os.environ.get("CLOUD_PROVIDER", "azure"))
    ap.add_argument("--model-name", required=True)
    ap.add_argument("--model-dir", type=Path, required=True)
    ap.add_argument("--decision", type=Path, required=True)
    ap.add_argument("--stage", default="staging")
    args = ap.parse_args()

    decision = json.loads(args.decision.read_text())
    if not decision.get("passed"):
        print(f"refusing to register: gate rejected this candidate ({decision.get('reason')})")
        return 3

    metrics = json.loads((args.model_dir / "metrics.json").read_text())
    if not (args.model_dir / "model.joblib").exists():
        print("model.joblib missing from the model directory")
        return 2

    tags = {
        "stage": args.stage,
        "seed": str(metrics.get("seed")),
        "data_fingerprint": str(metrics.get("data_fingerprint")),
        "data_version": str(metrics.get("data_version")),
        "git_commit": str(metrics.get("git_commit")),
        "image_digest": str(metrics.get("image_digest")),
        "metric_val": str(metrics.get("val_roc_auc")),
        "metric_test": str(metrics.get("test_roc_auc")),
        "metric_val_pr": str(metrics.get("val_pr_auc")),
        "metric_test_pr": str(metrics.get("test_pr_auc")),
        "gate_reason": decision.get("reason", "")[:200],
        "pipeline_run_id": os.environ.get("AZUREML_ROOT_RUN_ID", "local"),
        "course": "itcs355", "lab": "5",
    }
    from cloudlayer import registry

    version = registry.register(args.provider, str(args.model_dir), args.model_name, tags,
                                f"Registered by the Lab 5 pipeline: {decision.get('reason', '')}")
    print(f"registered {args.model_name}:{version} stage={args.stage}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
