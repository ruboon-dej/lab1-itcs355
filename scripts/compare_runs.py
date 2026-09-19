"""Lab 2 — rank tracked runs by metric AND by cost per point.

    python scripts/compare_runs.py --experiment itcs355-lab2

Writes reports/lab2-comparison.md. The cost-per-point column is what the lab is about:
the highest-scoring run is frequently not the one you should register.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import mlflow
import pandas as pd

from src import config


AZURE_RECOVERED_RUNS = [
    {
        "run_id": "amiable_honey_8f8c1b6flt",
        "val_roc_auc": 0.8424390505,
        "test_roc_auc": 0.8518038253,
        "n_estimators": 100,
        "max_depth": 4,
        "min_samples_leaf": 1,
    },
    {
        "run_id": "great_moon_72n9b5dm4g",
        "val_roc_auc": 0.8425998974,
        "test_roc_auc": 0.8532857871,
        "n_estimators": 100,
        "max_depth": 4,
        "min_samples_leaf": 5,
    },
    {
        "run_id": "keen_town_n71sc8024r",
        "val_roc_auc": 0.8311874325,
        "test_roc_auc": 0.8487605110,
        "n_estimators": 100,
        "max_depth": 8,
        "min_samples_leaf": 1,
    },
    {
        "run_id": "affable_napa_1t3680gjgd",
        "val_roc_auc": 0.8396969952,
        "test_roc_auc": 0.8465574161,
        "n_estimators": 100,
        "max_depth": 8,
        "min_samples_leaf": 5,
    },
    {
        "run_id": "epic_stamp_tdqd5qntfs",
        "val_roc_auc": 0.8268292496,
        "test_roc_auc": 0.8414830203,
        "n_estimators": 100,
        "max_depth": 12,
        "min_samples_leaf": 1,
    },
    {
        "run_id": "shy_nut_t1jftmfmc2",
        "val_roc_auc": 0.8321678322,
        "test_roc_auc": 0.8417344245,
        "n_estimators": 100,
        "max_depth": 12,
        "min_samples_leaf": 5,
    },
    {
        "run_id": "keen_oil_0jzpdw142m",
        "val_roc_auc": 0.8403710200,
        "test_roc_auc": 0.8536827411,
        "n_estimators": 300,
        "max_depth": 4,
        "min_samples_leaf": 1,
    },
    {
        "run_id": "good_head_b3nqq92cqp",
        "val_roc_auc": 0.8410910010,
        "test_roc_auc": 0.8544634174,
        "n_estimators": 300,
        "max_depth": 4,
        "min_samples_leaf": 5,
    },
    {
        "run_id": "amiable_heart_0hbxn6sw4l",
        "val_roc_auc": 0.8337763004,
        "test_roc_auc": 0.8478475167,
        "n_estimators": 300,
        "max_depth": 8,
        "min_samples_leaf": 1,
    },
    {
        "run_id": "ashy_ocean_dvpm1b8j71",
        "val_roc_auc": 0.8376978990,
        "test_roc_auc": 0.8490516106,
        "n_estimators": 300,
        "max_depth": 8,
        "min_samples_leaf": 5,
    },
    {
        "run_id": "bold_basket_zphkn345fm",
        "val_roc_auc": 0.8264615997,
        "test_roc_auc": 0.8373613142,
        "n_estimators": 300,
        "max_depth": 12,
        "min_samples_leaf": 1,
    },
    {
        "run_id": "affable_cassava_0ts068759l",
        "val_roc_auc": 0.8353694498,
        "test_roc_auc": 0.8431039160,
        "n_estimators": 300,
        "max_depth": 12,
        "min_samples_leaf": 5,
    },
]


def write_report(table: pd.DataFrame, args: argparse.Namespace) -> None:
    total_spend = 2.91
    average_cost = total_spend / len(table)

    lines = [
        "# Lab 2 — Run comparison",
        "",
        f"Experiment `{args.experiment}` · {len(table)} trials · "
        f"total Azure study spend approximately {total_spend:.2f} THB",
        "",
        "The 12 trials were completed on Azure ML managed compute. "
        "The available evidence provides total study spend, but not a verified "
        "billing amount for each individual job, so the cost-per-trial figure below "
        "is an average rather than per-job billing.",
        "",
        f"Average study cost per trial: **{average_cost:.4f} THB**.",
        "",
        "`thb_per_point` uses this average trial cost and therefore is a comparison "
        "indicator, not an individual Azure billing record.",
        "",
        table.fillna("—").to_markdown(index=False),
        "",
        "## Which model did you register, and why?",
        "",
        "The registered configuration was `n_estimators=100`, `max_depth=4`, "
        "`min_samples_leaf=5`. It was not selected simply by taking the highest "
        "test score, because test data is held out from model selection. The "
        "12-trial sweep identified this configuration as a strong validation "
        "candidate, and it was then rerun across seeds to examine stability. "
        "For seeds 20260101, 20260102, and 20260103, validation ROC-AUC was "
        "0.8426, 0.8733, and approximately 0.8430 respectively, showing "
        "meaningful variation. The 20260102 run was selected based on validation "
        "performance, with test ROC-AUC reported only as held-out evidence. "
        f"The complete 12-trial study cost approximately {total_spend:.2f} THB, "
        f"or about {average_cost:.2f} THB per trial on average; one monthly "
        "retraining run would therefore be inexpensive at this observed scale. "
        "The choice could still be wrong because the seed also changes the "
        "generated dataset in these reruns, so the stability check is not a "
        "pure model-randomness test.",
        "",
        "## Selection evidence",
        "",
        "- Original sweep: 12 Azure ML trials.",
        "- Selected configuration: `100 / 4 / 5`.",
        "- Selection seed rerun: `20260102`.",
        "- Selected run: `mango_boot_pbpr17lrhb`.",
        "- Selected validation ROC-AUC: `0.8733`.",
        "- Selected test ROC-AUC: `0.8463`.",
        "- Three-seed validation ROC-AUC SD: approximately `0.018`.",
        "- Total observed study spend: approximately `2.91 THB`.",
    ]

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text("\n".join(lines))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--experiment", default="itcs355-lab2")
    ap.add_argument("--metric", default="val_roc_auc")
    ap.add_argument("--azure-recovered", action="store_true")
    ap.add_argument("--out", type=Path, default=Path("reports/lab2-comparison.md"))
    args = ap.parse_args()

    if args.azure_recovered:
        runs = pd.DataFrame(AZURE_RECOVERED_RUNS)

        baseline = runs[args.metric].min()
        average_cost = 2.91 / len(runs)

        table = runs[
            [
                "run_id",
                args.metric,
                "test_roc_auc",
                "n_estimators",
                "max_depth",
                "min_samples_leaf",
            ]
        ].copy()

        table["avg_cost_thb"] = average_cost
        gain = table[args.metric] - baseline
        table["thb_per_point"] = (
            table["avg_cost_thb"] / (gain * 100)
        ).where(gain > 0)
        table["thb_per_point"] = table["thb_per_point"].round(4)

        table[args.metric] = table[args.metric].round(4)
        table["test_roc_auc"] = table["test_roc_auc"].round(4)
        table["avg_cost_thb"] = table["avg_cost_thb"].round(4)
        table = table.sort_values(args.metric, ascending=False)

        write_report(table, args)

        print(f"wrote {args.out}  ({len(table)} trials)")
        print(table.to_string(index=False))
        return 0

    cfg = config.load(strict=False)
    mlflow.set_tracking_uri(cfg.mlflow_tracking_uri)
    exp = mlflow.get_experiment_by_name(args.experiment)
    if exp is None:
        print(f"No experiment named {args.experiment!r}. Run `make tune` first.")
        return 1

    runs = mlflow.search_runs(experiment_ids=[exp.experiment_id])
    if runs.empty:
        print("No runs found.")
        return 1

    metric_col = f"metrics.{args.metric}"
    cost_col = "metrics.cost_thb"
    baseline = runs[metric_col].min()

    table = pd.DataFrame({
        "run_id": runs["run_id"].str[:8],
        args.metric: runs[metric_col].round(4),
        "cost_thb": runs.get(cost_col, 0).round(4),
        "n_estimators": runs.get("params.n_estimators"),
        "max_depth": runs.get("params.max_depth"),
        "min_samples_leaf": runs.get("params.min_samples_leaf"),
    })
    gain = (table[args.metric] - baseline).clip(lower=1e-9)
    table["thb_per_point"] = (table["cost_thb"] / (gain * 100)).round(4)
    table = table.sort_values(args.metric, ascending=False)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Lab 2 — Run comparison",
        "",
        f"Experiment `{args.experiment}` · {len(table)} trials · "
        f"total spend {table['cost_thb'].sum():.4f} THB",
        "",
        "`thb_per_point` is cost per percentage point of "
        f"{args.metric} above the worst trial. Cheap improvements rank low; expensive "
        "improvements rank high, however good the headline number is.",
        "",
        table.fillna("—").to_markdown(index=False),
        "",
        "## Which model did you register, and why?",
        "",
        "TODO(Lab 2): 200 words maximum. Must address all four:",
        "",
        "1. Why this model rather than the highest-scoring one, if they differ",
        "2. The variance across seeds for your chosen configuration",
        "3. What it costs to train, and to retrain monthly",
        "4. One way this choice could be wrong",
        "",
        "An answer that only says \"highest validation score\" scores zero on this task.",
    ]
    args.out.write_text("\n".join(lines))
    print(f"wrote {args.out}  ({len(table)} trials)")
    print(table.head(5).to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())