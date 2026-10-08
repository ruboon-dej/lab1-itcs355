"""Lab 4 — drift detection.

PSI and Kolmogorov–Smirnov, implemented directly so you can see what the numbers mean.
Evidently is allowed instead, but you must still be able to explain what your chosen
statistic measures and why your threshold is what it is.

    python -m monitoring.drift --reference data/raw/sensors.csv --current data/current.csv

A threshold copied from a tutorial is not a justified threshold, and Lab 4 grades the
justification, not the code.
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
import pandas as pd

# Conventional PSI reading, and it IS only conventional — it comes from credit scoring,
# where features are stable and volumes are large. Your problem may warrant something
# tighter or looser. TODO(Lab 4): state your threshold and why, in your README.
PSI_NO_CHANGE = 0.10
PSI_MODERATE = 0.25


@dataclass
class FeatureDrift:
    feature: str
    psi: float
    ks_statistic: float
    ref_mean: float
    cur_mean: float
    verdict: str


def psi(reference: np.ndarray, current: np.ndarray, bins: int = 10) -> float:
    """Population Stability Index.

    Bins the reference into quantiles and compares the proportion of mass falling in each.
    Sensitive to changes in shape, not only in mean — which is why a feature can drift
    badly while its average looks untouched.
    """
    edges = np.quantile(reference, np.linspace(0, 1, bins + 1))
    edges[0], edges[-1] = -np.inf, np.inf
    edges = np.unique(edges)
    if len(edges) < 3:
        return 0.0

    ref_counts, _ = np.histogram(reference, bins=edges)
    cur_counts, _ = np.histogram(current, bins=edges)

    # Laplace smoothing: an empty bin would otherwise make the log term infinite.
    ref_prop = (ref_counts + 1) / (ref_counts.sum() + len(ref_counts))
    cur_prop = (cur_counts + 1) / (cur_counts.sum() + len(cur_counts))

    return float(np.sum((cur_prop - ref_prop) * np.log(cur_prop / ref_prop)))


def ks_statistic(reference: np.ndarray, current: np.ndarray) -> float:
    """Two-sample Kolmogorov–Smirnov statistic: the largest gap between the two CDFs.

    Complements PSI. KS is more sensitive to a shift in location; PSI to a change in shape.
    Reporting both, and noticing when they disagree, is worth more than either alone.
    """
    ref = np.sort(reference)
    cur = np.sort(current)
    pooled = np.concatenate([ref, cur])
    cdf_ref = np.searchsorted(ref, pooled, side="right") / len(ref)
    cdf_cur = np.searchsorted(cur, pooled, side="right") / len(cur)
    return float(np.max(np.abs(cdf_ref - cdf_cur)))


def verdict_for(score: float) -> str:
    if score < PSI_NO_CHANGE:
        return "stable"
    if score < PSI_MODERATE:
        return "moderate"
    return "significant"


def compare(reference: pd.DataFrame, current: pd.DataFrame, features: list[str]) -> list[FeatureDrift]:
    results = []
    for feature in features:
        ref = reference[feature].to_numpy(dtype=float)
        cur = current[feature].to_numpy(dtype=float)
        score = psi(ref, cur)
        results.append(FeatureDrift(
            feature=feature,
            psi=round(score, 5),
            ks_statistic=round(ks_statistic(ref, cur), 5),
            ref_mean=round(float(ref.mean()), 4),
            cur_mean=round(float(cur.mean()), 4),
            verdict=verdict_for(score),
        ))
    return sorted(results, key=lambda r: r.psi, reverse=True)


def main() -> int:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from src import config, data

    ap = argparse.ArgumentParser()
    ap.add_argument("--reference", type=Path, default=Path("data/raw/sensors.csv"))
    ap.add_argument("--current", type=Path, required=True)
    ap.add_argument("--threshold", type=float, default=PSI_MODERATE,
                    help="alert above this PSI. Justify your value in the README.")
    ap.add_argument("--out", type=Path, default=Path("reports/drift.json"))
    ap.add_argument("--emit", action="store_true", help="send scores as cloud metrics")
    ap.add_argument("--pushgateway", default=None,
                    help="host:port of a Prometheus Pushgateway; feeds the local dashboard")
    args = ap.parse_args()

    reference = pd.read_csv(args.reference)
    current = pd.read_csv(args.current)
    results = compare(reference, current, data.FEATURES)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps([asdict(r) for r in results], indent=2))

    print(f"{'feature':<22}{'psi':>10}{'ks':>10}  verdict")
    for r in results:
        print(f"{r.feature:<22}{r.psi:>10.5f}{r.ks_statistic:>10.5f}  {r.verdict}")

    if args.emit:
        # A failed metric write must never hide a drift alert: report it and carry on.
        try:
            from cloudlayer.factory import get_adapter
            adapter = get_adapter(config.load(strict=False))
            for r in results:
                adapter.emit_metric(f"drift.psi.{r.feature}", r.psi)
            print("metrics handed to the cloud exporter (delivery is confirmed in the provider, not here)")
        except Exception as exc:  # noqa: BLE001
            print(f"WARNING  metric emit failed: {exc}")

    if args.pushgateway:
        try:
            from prometheus_client import CollectorRegistry, Gauge, push_to_gateway
            registry = CollectorRegistry()
            g_psi = Gauge("drift_psi", "PSI of a feature against the reference window", ["feature"], registry=registry)
            g_ks = Gauge("drift_ks", "KS statistic of a feature against the reference window", ["feature"], registry=registry)
            for r in results:
                g_psi.labels(r.feature).set(r.psi)
                g_ks.labels(r.feature).set(r.ks_statistic)
            push_to_gateway(args.pushgateway, job="drift", registry=registry)
            print(f"pushed to Pushgateway at {args.pushgateway}")
        except Exception as exc:  # noqa: BLE001
            print(f"WARNING  pushgateway failed: {exc}")

    breached = [r for r in results if r.psi >= args.threshold]
    if breached:
        print(f"\nALERT  {len(breached)} feature(s) above threshold {args.threshold}: "
              + ", ".join(r.feature for r in breached))
        print("Before you retrain: is this drift, or is it a broken upstream pipeline? "
              "Retraining on corrupted data destroys a working model faster than any "
              "schedule would.")
        return 2
    print(f"\nOK  no feature above threshold {args.threshold}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
