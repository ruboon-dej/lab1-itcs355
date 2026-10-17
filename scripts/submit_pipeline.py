"""Compile and submit the Lab 5 pipeline.

    python scripts/submit_pipeline.py --dry-run
    python scripts/submit_pipeline.py --wait
    python scripts/submit_pipeline.py --wait --n-estimators 1 --max-depth 1     # weak model: gate must reject
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
    ap.add_argument("--dry-run", action="store_true", help="compile only; touches nothing")
    ap.add_argument("--wait", action="store_true")
    ap.add_argument("--no-compute", action="store_true", help="do not create/update the cluster")
    for name, typ in (("data-seed", int), ("model-seed", int), ("n-estimators", int),
                      ("max-depth", int), ("min-samples-leaf", int),
                      ("floor", float), ("margin", float)):
        ap.add_argument(f"--{name}", type=typ)
    ap.add_argument("--allow-bootstrap", choices=["true", "false"])
    args = ap.parse_args()

    from cloudlayer import azure_ops, pipelines

    spec = pipelines.load_spec()
    overrides = {k: getattr(args, k) for k in (
        "data_seed", "model_seed", "n_estimators", "max_depth", "min_samples_leaf",
        "floor", "margin", "allow_bootstrap") if getattr(args, k) is not None}
    job = pipelines.compile_azure(spec=spec, overrides=overrides)
    imgs = pipelines.images()
    print(f"train image: {imgs['train']}\nops image:   {imgs['ops']}")
    print(f"parameters:  { {**spec['parameters'], **overrides} }")
    if args.dry_run:
        print("dry run: nothing submitted")
        return 0

    for key in ("AZURE_SUBSCRIPTION_ID", "AZURE_RESOURCE_GROUP", "AZURE_ML_WORKSPACE",
                "TRAIN_UAI_ID", "TRAIN_UAI_CLIENT_ID"):
        if not os.environ.get(key):
            print(f"missing environment variable {key}")
            return 2
    if "<run" in imgs["train"] or "<run" in imgs["ops"]:
        print("image references are placeholders: run make image-push and make image-ops-push first")
        return 2

    if not args.no_compute:
        c = spec["compute"]
        name = os.environ.get("TRAIN_COMPUTE", "itcs355-lab5-cpu")
        tags = config.load(strict=False).tags(5)
        azure_ops.ensure_cluster(name, c["instance"], tags, os.environ["TRAIN_UAI_ID"],
                                 c["min_nodes"], c["max_nodes"], c["idle_seconds"])
        print(f"compute {name} ready ({c['instance']}, dedicated, min {c['min_nodes']}, tagged lab=5)")

    created = pipelines.submit(job, spec["experiment"])
    print(f"submitted {created.name}\n{created.studio_url}")
    if args.wait:
        status = pipelines.wait(created.name)
        print(f"final status: {status}")
        return 0 if status == "Completed" else 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
