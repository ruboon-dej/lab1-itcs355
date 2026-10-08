"""Lab 4 — turn the portable monitoring/dashboard.json into a Grafana-native dashboard.

    python scripts/build_grafana_dashboard.py

One source of truth (dashboard.json); the Grafana file is generated, so the two cannot drift.
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "monitoring" / "dashboard.json"
OUT = ROOT / "monitoring" / "grafana" / "dashboards" / "itcs355.json"
LEGEND = {"status_class": "{{status_class}}", "version": "{{version}}", "feature": "{{feature}}"}


def _legend(expr: str) -> str:
    for label, template in LEGEND.items():
        if label in expr or expr in ("model_version_info", "drift_psi", "feature_rolling_mean"):
            if expr == "model_version_info":
                return LEGEND["version"]
            if expr in ("drift_psi", "feature_rolling_mean"):
                return LEGEND["feature"]
            if label == "status_class":
                return template
    return ""


def main() -> int:
    spec = json.loads(SRC.read_text())
    panels = []
    for i, p in enumerate(spec["panels"]):
        exprs = p.get("targets") or [p["target"]]
        names = ["p50", "p95", "p99"] if len(exprs) == 3 else [None] * len(exprs)
        panels.append({
            "id": p["id"],
            "type": p["type"],
            "title": p["title"],
            "description": p.get("_note", ""),
            "gridPos": {"h": 8, "w": 12, "x": 12 * (i % 2), "y": 8 * (i // 2)},
            "datasource": {"type": "prometheus", "uid": "prometheus"},
            "fieldConfig": {"defaults": {"unit": p.get("unit", "short")}, "overrides": []},
            "targets": [
                {"refId": chr(65 + j), "expr": e, "legendFormat": names[j] or _legend(e),
                 "instant": p["type"] == "stat"}
                for j, e in enumerate(exprs)
            ],
        })
    dashboard = {
        "uid": "itcs355", "title": spec["title"], "refresh": spec.get("refresh", "30s"),
        "schemaVersion": 39, "time": {"from": "now-30m", "to": "now"}, "panels": panels,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(dashboard, indent=2) + "\n")
    print(f"wrote {OUT.relative_to(ROOT)} ({len(panels)} panels)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
