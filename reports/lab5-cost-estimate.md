# Lab 5 cost estimate (written before any Lab 5 resource is run)

This file is the prediction required by Task 5, item 1. It is committed before Task 1 starts
and is not edited afterwards. The comparison with billing lives in `reports/lab5-cost.md`.

Scope: spend caused by Lab 5 work only. Earlier labs are excluded, but the container registry
is shared and is counted for the days Lab 5 is active.

## Rates used

Prices come from the Azure Retail Prices API, region japaneast, Linux, pay-as-you-go,
queried on 2026-10-16. THB conversion uses 33.32 THB per USD, the same rate as `src/costs.py`.

| Item | USD | THB |
|---|---|---|
| Standard_DS3_v2, dedicated | 0.409 / hour | 13.63 / hour |
| Standard_DS2_v2, dedicated | 0.205 / hour | 6.83 / hour |
| Container Registry, Basic | 0.1666 / day | 5.55 / day |
| Container Apps, active vCPU | 0.000024 / second | 0.0008 / second |
| Container Apps, active memory | 0.000003 / GiB-second | 0.0001 / GiB-second |
| gpt-4.1-mini tokens | not yet verified | verify before the Part B cost figures |

Low-priority and spot compute are not used: the Azure ML low-priority quota is 0.

## Assumptions

- Lab 5 stays active for 5 calendar days (build, two days of billing lag, teardown check).
- 8 pipeline runs: dummy condition test, happy path, deliberate reject path, schedule test,
  and four reruns for fixes.
- Each run bills about 15 minutes of DS3_v2 plus 2 minutes of idle before scale-down.
- Serving: 0.5 vCPU and 1 GiB for about 10 active minutes in total (deploys and load tests).
- LLM step: about 60 calls and 36,000 tokens in total on gpt-4.1-mini.

## Estimate by component

| Component | Working | THB |
|---|---|---|
| Training and pipeline compute | 8 runs x 17 min x 13.63 THB/h | 31 |
| Serving | 600 s x (0.5 vCPU x 0.0008 + 1 GiB x 0.0001) | 1 |
| Registry | 5 days x 5.55 | 28 |
| Storage | a few MB of artifacts and logs | under 1 |
| Monitoring | inside the free ingestion allowance | 0 |
| LLM tokens | about 36k tokens, price unverified | under 1 |
| **Total** | | **about 60** |

Plausible range: 45 to 90 THB.

## What would make this wrong

- More pipeline runs than 8, or a failed run that holds a node until timeout.
- A cluster left with a non-zero minimum node count.
- Billing granularity and lag: small amounts may show late or be rounded.
- The registry dominates the total, so every extra day adds 5.55 THB regardless of the work done.
- The exchange rate and the gpt-4.1-mini price were not re-verified when this was written.
