# Lab 5 cost report

Prices: Azure Retail Prices API, region japaneast, Linux, pay-as-you-go, read on 2026-10-17.
THB conversion: 33.32 THB per USD (the rate in `src/costs.py`). Everything in this file is
reproducible from `docs/lab5/`. Cells marked PENDING-BILLING are filled from
`docs/lab5/actual-cost.txt` once Azure Cost Management has settled (at least one day after
the last compute run on 2026-10-17).

## 1. Estimate before running

Written and committed before Task 1 started: `reports/lab5-cost-estimate.md`, commit `72b2d38`.

| Component | Estimate (THB) | Working |
|---|---|---|
| Training and pipeline compute | 31 | 8 runs x 17 min x 13.63 THB/h (DS3_v2) |
| Serving | 1 | 10 active minutes at 0.5 vCPU / 1 GiB |
| Registry | 28 | 5 days x 5.55 THB/day |
| Storage | under 1 | a few MB |
| Monitoring | 0 | inside the free ingestion allowance |
| LLM tokens | under 1 | about 60 calls, about 36k tokens |
| **Total** | **about 60** | plausible range 45 to 90 |

## 2. Actual, from billing

Command: `bash scripts/lab5_actual_cost.sh 2026-10-16 2026-10-20` (output saved in
`docs/lab5/actual-cost.txt`).

| Scope | Actual (THB) |
|---|---|
| Resources tagged `lab=5` (by resource) | PENDING-BILLING |
| Container registry (created before Lab 5, carries only `course=itcs355`, so queried by resource) | PENDING-BILLING |
| Whole resource group, by service | PENDING-BILLING |
| **Lab 5 total (tagged + registry share for the Lab 5 days)** | PENDING-BILLING |

## 3. The gap

Usage-based reconstruction from the run history (`docs/lab5/run-durations.txt`), to be compared
with the billed figures above:

| Component | Estimate | Usage-based reconstruction | Why they differ |
|---|---|---|---|
| Pipeline compute | 31 | about 12.3 | 12 pipeline runs, total wall time 83.7 min, plus about 2 min of idle scale-down per run, gives 1.80 node-hours on `Standard_DS2_v2` at 6.83 THB/h. The estimate assumed `Standard_DS3_v2` at 13.63 THB/h and 17 minutes per run; the runs averaged 7.0 minutes. More runs than planned (12, not 8, because of the condition-node attempt, the permission experiments and the scheduled runs) did not offset the halved rate and shorter runs. |
| Serving | 1 | 0 | No serving deployment was made in Lab 5. Rollout is by the Lab 4 CD path, which I did not exercise. |
| LLM tokens | under 1 | about 1.1 | About 170 live calls (baseline, re-records, degraded, short-prompt and cap runs), roughly 64k input and 5.4k output tokens at list price. This is an approximation: some fixtures were overwritten by re-runs. |
| Registry | 28 | 5.55 per day | Depends on how many days it exists; Lab 5 spanned two calendar days. |
| Storage, monitoring | under 1 | PENDING-BILLING | |

Paragraph for the billing comparison (finish once the figures are in): compute came in well
below the estimate because the estimate used an instance twice as expensive and runs more than
twice as long as they turned out to be. The registry is the largest single line and is
independent of how much work was done. Anything billed that this table does not explain, such
as storage transactions or log ingestion from job logs, I did not predict. PENDING-BILLING.

## 4. Breakdown by component

| Component | Estimate | Usage-based | Billed |
|---|---|---|---|
| Training and pipeline compute (Azure ML cluster, tagged `lab=5`) | 31 | 12.3 | PENDING-BILLING |
| Storage (workspace storage, artifacts) | under 1 | not measured | PENDING-BILLING |
| Serving (Container Apps) | 1 | 0 | PENDING-BILLING |
| Pipeline orchestration (Azure ML pipelines and schedules have no separate charge) | 0 | 0 | PENDING-BILLING |
| Monitoring (Log Analytics, Application Insights) | 0 | not measured | PENDING-BILLING |
| LLM tokens (Azure OpenAI, `gpt-4.1-mini` Global Standard) | under 1 | about 1.1 | PENDING-BILLING |
| Registry (shared, Basic SKU) | 28 | 5.55 per day | PENDING-BILLING |

## 5. Cost per 1,000 predictions at three utilisation assumptions

Serving model: Azure Container Apps, 0.5 vCPU and 1 GiB, scale to zero.
Cost per active second = 0.5 x $0.000024 + 1 x $0.000003 = $0.000015 = 0.000500 THB.
Capacity: 10.43 requests/s, the highest Lab 3 rate with a 0% error rate (2 virtual users,
p95 258 ms, which is above the 200 ms target). Utilisation here means the share of billed
active time spent serving requests. Cost per 1,000 predictions =
1000 / (10.43 x utilisation) x 0.000500 THB, plus the request meter ($0.40 per million, 0.0133 THB per 1,000).

| Utilisation | Active seconds per 1,000 | Compute (THB) | + requests | **THB per 1,000 predictions** | Always-on DS2_v2 for comparison |
|---|---|---|---|---|---|
| 5% | 1917.5 | 0.9584 | 0.0133 | **0.9717** | 5.69 |
| 25% | 383.5 | 0.1917 | 0.0133 | **0.2050** | 1.14 |
| 80% | 119.8 | 0.0599 | 0.0133 | **0.0732** | 0.36 |

The always-on column uses the corrected DS2_v2 rate (6.83 THB/h) and the Lab 3 throughput of
6.67 predictions/s. It replaces the earlier Lab 3 figures, which used a wrong rate.
Limits of this table: free monthly grants and idle-replica charges are ignored, and the
meter rates should be re-verified before anyone relies on them.

The LLM step is a different cost shape. At the measured usage (377 input and 32 output
tokens per request, nothing cached) it costs **6.73 THB per 1,000 requests**, about 92 times the
serving compute at 80% utilisation, and it does not fall as utilisation rises.

## 6. One optimisation applied

Shorter rationale in the triage prompt (50 words down to 20), gated by the golden set.

| | Before (prompt v2) | After (20-word prompt) |
|---|---|---|
| Tokens in / out / cached | 377 / 32 / 0 | 377 / 25 / 0 |
| THB per 1,000 requests | 6.7313 | 6.3582 |
| THB per month at 1,000 requests/day | 201.9 | 190.7 |
| Golden set | 15/15 | 15/15, gate PASSED |

Saving: 0.373 THB per 1,000 requests, 5.5%, about 11.2 THB a month at 1,000 requests a day.
Evidence: `docs/lab5/llm-short-gate.txt`, `docs/lab5/token-numbers.txt`.
What it gives up: less explanation in each answer, which the golden set does not measure.
Tried and not worth it: a 60-token output cap saves nothing at this usage (the longest answer
was 41 tokens) and only bounds the worst case (8.22 versus 15.69 THB per 1,000 if every reply
ran to the cap); a degraded prompt looked cheaper (4.83 THB per 1,000) but failed five golden
cases, which is the kind of saving the gate exists to refuse.
Compute choice, not measured as a before/after: the pipeline ran on DS2_v2 (6.83 THB/h) rather than
the DS3_v2 (13.63 THB/h) assumed in the estimate.
