# Lab 5 cost report

Prices: Azure Retail Prices API, region japaneast, Linux, pay-as-you-go, read on 2026-10-17.
THB conversion: 33.32 THB per USD (the rate in `src/costs.py`). Billed figures come from Azure
Cost Management (portal, Cost analysis) on 2026-10-19: scope = resource group `itcs355-6688022`,
period 14 to 19 October, grouped by resource, in USD (`docs/lab5/cost-analysis.png`). The
Cost Management query API returned HTTP 429 for every retry (`docs/lab5/actual-cost.txt`), so the
portal view is the source. The portal rounds to cents, so small lines are shown as "under $0.01".

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

| Resource (type) | USD | THB |
|---|---|---|
| Container registry `itcs3556688022` (Basic, shared, tagged only `course=itcs355`) | 0.81 | 27.0 |
| Azure ML workspace `itcs355-6688022-ws` (the pipeline cluster's compute is billed on this line) | 0.44 | 14.7 |
| Azure OpenAI account `itcs355-6688022-aoai` (Cognitive Services) | 0.03 | 1.0 |
| Storage account | under 0.01 | about 0 |
| Key Vault | under 0.01 | about 0 |
| **Total, resource group, 14 to 19 October** | **1.28** | **42.7** |

Notes on this table:
- The period starts on 14 October, two days before Lab 5 work began, because that was the portal's
  default window. The only line that can contain pre-Lab-5 cost is the registry, which exists
  whether or not any work is done. The workspace line has no other known usage in the window.
- I could not produce a view filtered by tag `lab=5`: the compute cluster carries the tag, but
  its cost appears on the workspace line, whose tags are not `lab=5`. A tag filter alone would
  have missed most of the Lab 5 spend. The OpenAI account line is the only tagged resource that
  shows separately.

## 3. The gap

**Against the 20% criterion:** the pre-run estimate (about 60 THB) is 29% above the billed 42.7 THB, so it does not meet it. The usage-based figures do: compute plus LLM reconstructed from run history is 13.4 THB against 15.7 THB billed (15% under), and compute alone is 12.3 against 14.7 (billed is 19.5% above the reconstruction, just inside the line). Details follow the table below.

The estimate was about 60 THB and the billed total is 42.7 THB, 17 THB or 29% lower, just below
the bottom of my 45 to 90 range.

| Component | Estimate | Billed | Difference | Reason |
|---|---|---|---|---|
| Pipeline compute | 31 | 14.7 | -16.3 | The estimate assumed `Standard_DS3_v2` (13.63 THB/h) and 17 minutes per run. The runs used `Standard_DS2_v2` (6.83 THB/h) and averaged 7 minutes. I ran 12 pipelines, not 8 (the failed condition-node attempt, the permission experiments and the scheduled runs), which did not make up the difference. |
| Serving | 1 | 0 | -1 | No serving deployment was made in Lab 5. |
| Registry | 28 | 27.0 | -1 | 5.55 THB a day; 27.0 THB is 4.9 days. The 14 to 19 October window has six calendar days, and the last one was incomplete when I read it. |
| LLM tokens | under 1 | 1.0 | about 0 | About 170 live calls, matching my reconstruction of about 1.1 THB. |
| Storage, Key Vault, monitoring | under 1 | about 0 | about 0 | Below the portal's rounding. |

Against my usage-based reconstruction, made after the runs from the run history
(`docs/lab5/run-durations.txt`), compute was 12.3 THB reconstructed (83.7 minutes of pipeline
wall time plus 2 minutes of idle scale-down per run on DS2_v2) and 14.7 THB billed, so billing is
20% higher. I did not measure why; the likeliest cause is node allocation and idle time outside
the pipeline's wall time, longer than my 2-minute assumption. Compute plus LLM reconstructed is
13.4 THB against 15.7 THB billed, 15% under. So the usage-based figures are within 20% of
billing, and the pre-run estimate is not: it was an overestimate, because it used a larger
instance and longer runs than I ended up needing.

## 4. Breakdown by component

| Component | Estimate | Usage-based | Billed |
|---|---|---|---|
| Training and pipeline compute (Azure ML cluster, billed on the workspace line) | 31 | 12.3 | 14.7 |
| Storage (workspace storage, artifacts) | under 1 | not measured | under 0.3 |
| Serving (Container Apps) | 1 | 0 | 0 |
| Pipeline orchestration (Azure ML pipelines and schedules have no separate charge) | 0 | 0 | 0 |
| Monitoring (Key Vault, logging; no separate line over a cent) | 0 | not measured | under 0.3 |
| LLM tokens (Azure OpenAI, `gpt-4.1-mini` Global Standard) | under 1 | 1.1 | 1.0 |
| Registry (shared, Basic SKU) | 28 | 5.55 per day | 27.0 |
| **Total** | **about 60** | | **42.7** |

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
Limits of this table: free monthly grants and idle-replica charges are ignored, no serving was
deployed in Lab 5 so none of this was billed or measured this week, and the meter rates should
be re-verified before anyone relies on them.

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

## 7. Context: the whole term

Azure Cost analysis for the subscription, 31 August to 19 October (`docs/lab5/term-spend.png`, `term-spend-breakdown.png`): **$25.52**, about 850 THB at 33.32 THB/USD (817 THB at 32). That is over the 800 THB term limit and the $25.00 budget. The Azure ML workspace line is $18.27 and the registry $6.98; Lab 5 was about $1.3 (5%). Lab 5 was not the cause of the overrun, but it is part of it: without Lab 5 the total would have been about $24.2.
