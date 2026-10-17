"""Lab 5 evaluation gate: should this candidate be registered?

    python scripts/evaluation_gate.py --metrics /tmp/m.json --incumbent 0.99     # exits 1

A candidate passes only if BOTH hold:
  1. it clears an absolute floor on the validation metric, and
  2. it beats the incumbent (the registered model tagged stage=production) by `margin`.

Design decisions, each one a graded choice:
  * Validation metric, not test. Selecting on test leaks the held-out set (Lab 2).
  * margin 0.0075 is about one seed's noise (Lab 2 README: 0.8493 +/- 0.0075). A margin
    below the noise floor makes the gate a coin flip.
  * Fail CLOSED. If the registry cannot be read, the candidate is rejected. A gate that
    passes when it cannot look is not a gate.
  * No production model yet is a legitimate state, but only with --allow-bootstrap, and
    only the floor applies. Turn bootstrap off after the first promotion.
  * Both models are compared on metrics measured on the SAME data seed (the pipeline pins
    data_seed). Metrics measured on different data draws are not comparable.

--pipeline-mode: always exit 0 once a decision is written, and publish it as a boolean
control output so the pipeline can branch. Crashes still exit non-zero and stop the run.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# registry tag that carries each metric (written by scripts/register_model.py)
METRIC_TAG = {"val_roc_auc": "metric_val", "test_roc_auc": "metric_test",
              "val_pr_auc": "metric_val_pr", "test_pr_auc": "metric_test_pr"}


def decide(candidate: float, floor: float, margin: float,
           incumbent: float | None, allow_bootstrap: bool) -> tuple[bool, str]:
    if candidate < floor:
        return False, f"candidate {candidate:.4f} is below the absolute floor {floor}"
    if incumbent is None:
        if allow_bootstrap:
            return True, (f"no production incumbent; bootstrap allowed, candidate {candidate:.4f} "
                          f"clears the floor {floor}")
        return False, "no production incumbent and bootstrap is not allowed"
    gain = candidate - incumbent
    if gain >= margin:
        return True, (f"candidate {candidate:.4f} beats incumbent {incumbent:.4f} "
                      f"by {gain:+.4f} (margin {margin})")
    return False, (f"candidate {candidate:.4f} does not beat incumbent {incumbent:.4f} "
                   f"by the margin {margin} (gain {gain:+.4f})")


def write_control(path: Path, passed: bool) -> None:
    """Boolean control output. Same convention as the SDK's own expression component:
    a directory gets a file called `output`, a path gets the file itself."""
    value = "True" if passed else "False"
    if path.is_dir():
        (path / "output").write_text(value)
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(value)


def _str2bool(text: str) -> bool:
    return str(text).strip().lower() in ("1", "true", "yes", "y")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--metrics", type=Path, required=True)
    ap.add_argument("--metric", default="val_roc_auc")
    ap.add_argument("--incumbent", type=float, default=None,
                    help="explicit incumbent metric; skips the registry lookup")
    ap.add_argument("--floor", type=float, default=0.75)
    ap.add_argument("--margin", type=float, default=0.0075)
    ap.add_argument("--allow-bootstrap", type=_str2bool, default=False)
    ap.add_argument("--provider", default=os.environ.get("CLOUD_PROVIDER", "azure"))
    ap.add_argument("--model-name", default=os.environ.get("MODEL_REGISTRY_NAME"))
    ap.add_argument("--compare-stage", default="production")
    ap.add_argument("--decision-out", type=Path)
    ap.add_argument("--control-out", type=Path)
    ap.add_argument("--pipeline-mode", action="store_true")
    args = ap.parse_args()

    metrics = json.loads(args.metrics.read_text())
    if args.metric not in metrics:
        print(f"metric {args.metric!r} not in {args.metrics}: {sorted(metrics)}")
        return 2
    candidate = float(metrics[args.metric])

    incumbent = args.incumbent
    incumbent_version = None
    lookup_error = None
    if incumbent is None and args.model_name:
        try:
            from cloudlayer import registry

            found = registry.incumbent(args.provider, args.model_name, args.compare_stage)
            if found is not None:
                incumbent_version, tags = found
                tag = METRIC_TAG.get(args.metric)
                if tag is None or tag not in tags:
                    lookup_error = (f"incumbent v{incumbent_version} has no {tag!r} tag; "
                                    "cannot compare, failing closed")
                else:
                    incumbent = float(tags[tag])
        except Exception as exc:  # noqa: BLE001 - fail closed on ANY lookup problem
            lookup_error = f"could not read the registry: {type(exc).__name__}: {exc}"

    if lookup_error:
        passed, reason = False, lookup_error
    else:
        passed, reason = decide(candidate, args.floor, args.margin, incumbent, args.allow_bootstrap)

    decision = {"passed": passed, "reason": reason, "metric": args.metric,
                "candidate": candidate, "incumbent": incumbent,
                "incumbent_version": incumbent_version, "floor": args.floor,
                "margin": args.margin, "bootstrap_allowed": args.allow_bootstrap}
    print(json.dumps(decision, indent=2))
    print(f"\nGATE {'PASSED' if passed else 'REJECTED'}: {reason}")

    if args.decision_out:
        args.decision_out.parent.mkdir(parents=True, exist_ok=True)
        args.decision_out.write_text(json.dumps(decision, indent=2))
    if args.control_out:
        write_control(args.control_out, passed)

    if args.pipeline_mode:
        return 0
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
