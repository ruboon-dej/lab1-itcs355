"""Show why a pipeline step failed: statuses for every step, and the log tail of failed ones.

    python scripts/job_logs.py <pipeline-job-name>          # logs of failed steps only
    python scripts/job_logs.py <pipeline-job-name> --all    # log tail of every step
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src import config  # noqa: E402,F401


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    show_all = "--all" in sys.argv[1:]
    if len(args) != 1:
        print(__doc__)
        return 2
    from cloudlayer import azure_ops

    client = azure_ops.ml_client()
    for child in client.jobs.list(parent_job_name=args[0]):
        label = child.display_name or child.name
        print(f"{label:<44} {child.status}  ({child.name})")
        if not show_all and str(child.status).split(".")[-1].capitalize() not in ("Failed", "Canceled"):
            continue
        err = getattr(child, "error", None)
        if err:
            print(f"  error: {err}")
        with tempfile.TemporaryDirectory() as tmp:
            try:
                client.jobs.download(name=child.name, download_path=tmp, all=True)
            except Exception as exc:  # noqa: BLE001
                print(f"  could not download logs: {exc}")
                continue
            logs = sorted(Path(tmp).rglob("std_log.txt")) or sorted(Path(tmp).rglob("stdout*.txt"))
            for log in logs[:1]:
                lines = log.read_text(errors="replace").splitlines()[-40:]
                print("  --- last lines of", log.name)
                print("\n".join("  " + ln for ln in lines))
    return 0


if __name__ == "__main__":
    sys.exit(main())
