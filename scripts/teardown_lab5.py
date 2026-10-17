"""Lab 5 teardown. Deletes everything tagged lab=5 plus the things tags cannot reach.

    python scripts/teardown_lab5.py                 # jobs, compute, staging app, schedules, OpenAI
    python scripts/teardown_lab5.py --identities    # also delete the train/serve identities

Deletion is asynchronous. Re-run `az resource list --tag lab=5` now, and again in 24 hours.
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src import config  # noqa: E402


def sh(cmd: list[str]) -> int:
    print("  $", " ".join(cmd))
    return subprocess.run(cmd).returncode


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--identities", action="store_true")
    args = ap.parse_args()

    cfg = config.load()
    rg = os.environ.get("AZURE_RESOURCE_GROUP", cfg.project_id)
    deleted: list[str] = []

    from cloudlayer.factory import get_adapter

    print("1. adapter teardown (jobs, compute, staging container app)")
    deleted += get_adapter(cfg).teardown(cfg.tags(5))

    print("2. schedules")
    try:
        from cloudlayer import azure_ops

        deleted += azure_ops.delete_schedules("itcs355-lab5")
    except Exception as exc:  # noqa: BLE001
        print(f"  could not remove schedules: {exc}")

    print("3. Azure OpenAI account (delete, then purge so the name is released)")
    aoai = os.environ.get("AOAI_NAME", f"itcs355-{cfg.project_id}-aoai")
    if sh(["az", "cognitiveservices", "account", "delete", "-g", rg, "-n", aoai]) == 0:
        deleted.append(f"openai:{aoai}")
        sh(["az", "cognitiveservices", "account", "purge", "-g", rg, "-n", aoai,
            "-l", cfg.region if cfg.region != "unset" else "japaneast"])

    if args.identities:
        print("4. identities")
        for ident in ("itcs355-train-uai", "itcs355-serve-uai"):
            if sh(["az", "identity", "delete", "-g", rg, "-n", ident]) == 0:
                deleted.append(f"identity:{ident}")

    print("\nDeleted / requested:", *deleted, sep="\n  ")
    print("\nStill carrying lab=5 (screenshot this; it must be empty, re-check in 24h):")
    sh(["az", "resource", "list", "--tag", "lab=5", "-o", "table"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
