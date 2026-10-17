"""Cheap proof that the conditional node routes (about 2 minutes of compute).

    python scripts/pipeline_condition_test.py --flag True  --wait   # yes_branch runs, no_branch skipped
    python scripts/pipeline_condition_test.py --flag False --wait   # no_branch runs, yes_branch skipped
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src import config  # noqa: E402,F401


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--flag", choices=["True", "False"], required=True)
    ap.add_argument("--wait", action="store_true")
    ap.add_argument("--make-cluster", action="store_true")
    args = ap.parse_args()
    from cloudlayer import azure_ops, pipelines

    if args.make_cluster:
        spec = pipelines.load_spec()
        c = spec["compute"]
        name = os.environ.get("TRAIN_COMPUTE", "itcs355-lab5-cpu")
        azure_ops.ensure_cluster(name, c["instance"], config.load(strict=False).tags(5),
                                 os.environ["TRAIN_UAI_ID"], c["min_nodes"], c["max_nodes"],
                                 c["idle_seconds"])
        print(f"compute {name} ready")
    job = pipelines.compile_condition_test(args.flag)
    created = pipelines.submit(job, "itcs355-lab5-condition-test")
    print(f"submitted {created.name}\n{created.studio_url}")
    if args.wait:
        print(f"final status: {pipelines.wait(created.name, timeout_s=900)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
