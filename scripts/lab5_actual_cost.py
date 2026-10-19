#!/usr/bin/env python3
"""Actual cost from Azure Cost Management for the Lab 5 resource group, retrying when throttled.

    python scripts/lab5_actual_cost.py --from 2026-10-16 --to 2026-10-20
    python scripts/lab5_actual_cost.py --from 2026-10-16 --to 2026-10-20 --by-service

One query, grouped by resource and by the `lab` tag, so the Lab 5 resources (tag lab=5) and the
shared registry (no lab tag) appear on separate lines. Cost Management throttles hard (HTTP 429),
so this waits and retries instead of failing; each retry just waits, it does not hammer the API.
"""
import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

FX = 33.32  # THB per USD, same rate as src/costs.py


def az(*args):
    r = subprocess.run(["az", *args], capture_output=True, text=True)
    return r.returncode, r.stdout, r.stderr


def query(url, body, tries, wait):
    for i in range(1, tries + 1):
        code, out, err = az("rest", "--method", "post", "--url", url, "--body", json.dumps(body))
        if code == 0:
            return json.loads(out)
        if "Too Many Requests" in err or "429" in err:
            print(f"  throttled (429), attempt {i}/{tries}; waiting {wait}s ...", flush=True)
            time.sleep(wait)
            continue
        print(err)
        sys.exit(1)
    print("still throttled after all retries: wait 15 minutes and rerun, or use the portal fallback")
    sys.exit(2)


def show(title, result, save_to):
    cols = [c["name"] for c in result["properties"]["columns"]]
    rows = [dict(zip(cols, r)) for r in result["properties"]["rows"]]
    cost_key = next((c for c in cols if c in ("Cost", "PreTaxCost")), cols[0])
    rows.sort(key=lambda r: -float(r[cost_key]))
    total = sum(float(r[cost_key]) for r in rows)
    cur = rows[0].get("Currency", "") if rows else ""
    print(f"\n=== {title}   (columns: {', '.join(cols)})")
    for r in rows:
        label = " | ".join(str(v).split("/providers/")[-1] if isinstance(v, str) and "/providers/" in v else str(v)
                           for k, v in r.items() if k not in (cost_key, "Currency"))
        print(f"  {float(r[cost_key]):10.4f} {cur}   {label}")
    thb = f"  = {total * FX:.2f} THB" if cur == "USD" else ""
    print(f"  {total:10.4f} {cur}   TOTAL{thb}")
    Path(save_to).write_text(json.dumps(result, indent=2))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="frm", required=True)
    ap.add_argument("--to", required=True)
    ap.add_argument("--rg", default="itcs355-6688022")
    ap.add_argument("--tries", type=int, default=8)
    ap.add_argument("--wait", type=int, default=120)
    ap.add_argument("--by-service", action="store_true")
    a = ap.parse_args()
    code, sub, err = az("account", "show", "--query", "id", "-o", "tsv")
    if code:
        print(err); sys.exit(1)
    url = (f"https://management.azure.com/subscriptions/{sub.strip()}/resourceGroups/{a.rg}"
           "/providers/Microsoft.CostManagement/query?api-version=2023-11-01")

    def body(groups):
        return {"type": "ActualCost", "timeframe": "Custom",
                "timePeriod": {"from": f"{a.frm}T00:00:00Z", "to": f"{a.to}T23:59:59Z"},
                "dataset": {"granularity": "None",
                            "aggregation": {"totalCost": {"name": "Cost", "function": "Sum"}},
                            "grouping": groups}}

    groups = ([{"type": "Dimension", "name": "ServiceName"}] if a.by_service else
              [{"type": "Dimension", "name": "ResourceId"}, {"type": "TagKey", "name": "lab"}])
    title = "by service" if a.by_service else "by resource and lab tag"
    out = "docs/lab5/actual-cost-service.json" if a.by_service else "docs/lab5/actual-cost.json"
    show(f"resource group {a.rg}, {a.frm} to {a.to}, {title}", query(url, body(groups), a.tries, a.wait), out)


if __name__ == "__main__":
    main()
