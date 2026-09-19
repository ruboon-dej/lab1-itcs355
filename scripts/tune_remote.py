"""Lab 2 — budgeted hyperparameter study, run for real on managed cloud compute.

Run:  python scripts/tune_remote.py --trials 12 --budget-thb 150

Same search grid as src.tune, but each trial is submitted as an actual Azure ML job via
the adapter (adapter.submit_training / adapter.wait_training) instead of being fit
in-process. Cost per trial is measured from real wall-clock job duration (submit -> job
reaching a terminal state), multiplied by the instance's hourly rate from src/costs.py.

Checkpointing matches src.tune: a completed trial is skipped on resume, and the study
stops submitting new trials once projected spend would exceed the budget (already-running
trials are allowed to finish).
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
import mlflow

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cloudlayer.factory import get_adapter
from src import config, costs, seeds
from src.tune import SEARCH_SPACE, grid


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="ITCS355 Lab 2 — budgeted study (remote)")
    p.add_argument("--trials", type=int, default=12, help="minimum 12 for the lab")
    p.add_argument("--budget-thb", type=float, default=150.0)
    p.add_argument("--instance", default="Standard_DS3_v2", help="key into src/costs.py PRICE_TABLE")
    p.add_argument("--seed", type=int, default=seeds.DEFAULT_SEED)
    p.add_argument("--image-uri-file", type=Path, default=Path(".image_uri"),
                   help="File written by `make image-push` with the digest-pinned image URI.")
    p.add_argument("--checkpoint", type=Path, default=Path("reports/tune_remote_checkpoint.json"),
                   help="Resume file. An interruption should cost minutes, not the run.")
    return p.parse_args()


def load_checkpoint(path: Path) -> dict:
    if path.exists():
        state = json.loads(path.read_text())
        state.setdefault("completed", [])
        state.setdefault("spent_thb", 0.0)
        state.setdefault("trials", [])
        return state

    return {
        "completed": [],
        "spent_thb": 0.0,
        "trials": [],
    }


def save_checkpoint(path: Path, state: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2))


def main() -> None:
    args = parse_args()
    cfg = config.load(strict=False)
    seeds.set_all(args.seed)

    if not args.image_uri_file.exists():
        raise SystemExit(f"No image URI found at {args.image_uri_file} — run `make image-push` first.")
    image_uri = args.image_uri_file.read_text().strip()

    adapter = get_adapter(cfg)
    rate = costs.hourly_rate(
        cfg.provider,
        args.instance,
        spot=True,
    )

    state = load_checkpoint(args.checkpoint)
    candidates = grid(SEARCH_SPACE)[: args.trials]

    skipped: list[dict] = []
    for i, params in enumerate(candidates):
        key = json.dumps(params, sort_keys=True)
        if key in state["completed"]:
            print(f"trial {i}: already done, skipping (resumed from checkpoint)")
            continue

        if state["spent_thb"] >= args.budget_thb:
            skipped.append(params)
            continue

        train_args = {
            "n-estimators": params["n_estimators"],
            "max-depth": params["max_depth"],
            "min-samples-leaf": params["min_samples_leaf"],
            "seed": args.seed,
        }

        print(f"trial {i}: submitting {params} ...")
        started = time.perf_counter()
        job_id = adapter.submit_training(image_uri, train_args)
        try:
            result = adapter.wait_training(job_id)
        except RuntimeError as e:
            elapsed_s = time.perf_counter() - started
            elapsed_h = elapsed_s / 3600.0
            trial_cost = elapsed_h * rate

            state["spent_thb"] += trial_cost
            state["completed"].append(key)

            trial_record = {
                "trial": i,
                "params": params,
                "seed": args.seed,
                "job_id": job_id,
                "mlflow_run_id": result["mlflow_run_id"],
                "data_fingerprint": result["data_fingerprint"],
                "data_version": result["data_version"],
                "git_commit": result["git_commit"],
                "image_digest": result["image_digest"],
                "instance_type": args.instance,
                "compute_tier": "low_priority",
                "duration_s": round(elapsed_s, 3),
                "training_duration_s": result["training_duration_s"],
                "cost_thb": round(trial_cost, 4),
                "val_roc_auc": result["val_roc_auc"],
                "val_pr_auc": result["val_pr_auc"],
                "test_roc_auc": result["test_roc_auc"],
                "test_pr_auc": result["test_pr_auc"],
            }

            state["trials"].append(trial_record)

            # Add controller-side cost and job lineage to the same persistent MLflow run.
            mlflow.set_tracking_uri(cfg.mlflow_tracking_uri)

            with mlflow.start_run(
                run_id=result["mlflow_run_id"]
            ):
                mlflow.log_metrics(
                    {
                        "duration_s": round(elapsed_s, 3),
                        "cost_thb": round(trial_cost, 4),
                    }
                )

                mlflow.set_tags(
                    {
                        "training_job_id": job_id,
                        "instance_type": args.instance,
                        "compute_tier": "low_priority",
                    }
                )

            save_checkpoint(args.checkpoint, state)

            print(
                f"trial {i}: {params} -> "
                f"job_id={job_id} "
                f"val_roc_auc={result['val_roc_auc']:.4f} "
                f"test_roc_auc={result['test_roc_auc']:.4f} "
                f"duration={elapsed_s:.1f}s "
                f"cost={trial_cost:.4f} THB "
                f"cumulative={state['spent_thb']:.4f}"
            )
            continue

        elapsed_h = (time.perf_counter() - started) / 3600.0
        trial_cost = elapsed_h * rate
        state["spent_thb"] += trial_cost
        state["completed"].append(key)
        save_checkpoint(args.checkpoint, state)

        print(f"trial {i}: {params} -> job_id={job_id} "
              f"duration={elapsed_h * 3600:.1f}s cost={trial_cost:.4f} THB  "
              f"cumulative={state['spent_thb']:.4f}  studio_url={result['studio_url']}")

    print(f"\nspent {state['spent_thb']:.4f} of {args.budget_thb} THB")
    if skipped:
        print(f"BUDGET EXHAUSTED — {len(skipped)} configurations not run:")
        for s in skipped:
            print(f"  {s}")
        print("Report this in your README. Which trials you could not afford is a finding, "
              "not an embarrassment.")


if __name__ == "__main__":
    main()
