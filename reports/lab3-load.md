# ITCS355 Lab 3 — Serving, Load Testing, and Rollback

## 1. Serving configuration

- Provider: Azure ML
- Region: Japan East
- Endpoint: `itcs355-itcs355-6688022-predict`
- Serving image: `itcs355-serve:11c521f`
- Production model: registry `itcs355-6688022`, version `2`
- Serving instance: `Standard_DS2_v2`, 1 instance
- Traffic: `blue=100`
- Model version is returned in every prediction response and `X-Model-Version` response header.
- `/health` is the liveness route; `/ready` checks model readiness; `/predict` is the scoring route.

## 2. Latency target and concurrency

The p95 target was declared **before measurement** as **<200 ms**.

Measurements used 60-second k6 runs against the Azure ML endpoint with the same single-prediction payload. Requests with non-200 responses were excluded from the custom latency metric.

| VUs | Requests | Throughput (req/s) | p50 (ms) | p95 (ms) | p99 (ms) | Error rate |
|---:|---:|---:|---:|---:|---:|---:|
| 1 | 365 | 6.08 | 146.0 | 233.0 | 236.4 | 0.00% |
| 2 | 627 | 10.43 | 186.0 | 258.0 | 269.9 | 0.00% |
| 3 | 765 | 12.69 | 236.4 | 302.5 | 332.9 | 2.09% |
| 5 | 1,611 | 26.75 | 239.7 | 302.0 | 333.8 | 52.57% |

The endpoint produced no failed requests at 1 or 2 VUs, although the p95 latency target was not met at either concurrency.

At 3 VUs, the error rate exceeded the pre-declared 1% failure threshold. The 5-VU run produced substantial failures and Azure HTTP/2 `INTERNAL_ERROR` responses.

The first tested concurrency exceeding the 1% error threshold was **3 VUs**. Therefore, the observed reliable operating range is between **2 and 3 VUs**, and the observed breaking point is between those two tested levels.

The 3- and 5-VU latency results should be interpreted cautiously because provider transport errors occurred at those loads.

## 3. Batch inference

A 100-row batch was compared with single-row requests on the same endpoint configuration.

- Batch size: 100
- Batch requests: 357
- Predictions processed: 35,700
- Batch request throughput: 5.9496 batches/s
- Prediction throughput: approximately **594.96 predictions/s**
- Batch p50: 140.8 ms
- Batch p95: 265.8 ms
- Batch p99: 461.0 ms
- Batch errors: 0%

Batching therefore processed approximately **80 times more predictions per second** than the single-prediction 1-VU test. However, the p95 of the batch request itself exceeded the pre-declared 200 ms request-latency target.

## 4. Payload-size experiment

At 1 VU, request JSON was inflated with legal JSON padding while keeping the prediction content unchanged.

| Payload | Requests | p50 (ms) | p95 (ms) | p99 (ms) | Error rate | Throughput (req/s) |
|---:|---:|---:|---:|---:|---:|---:|
| 1 KB | 444 | 124.6 | 164.2 | 220.2 | 0% | 7.40 |
| 10 KB | 426 | 129.8 | 212.2 | 266.9 | 0% | 7.09 |
| 100 KB | 53 | 941.4 | 2,029.3 | 2,349.3 | 0% | 0.88 |
| 500 KB | 87 | 521.9 | 1,384.1 | 1,578.7 | 0% | 1.43 |

The 1 KB payload met the p95 target. At 10 KB the p95 slightly exceeded the target, while the 100 KB and 500 KB payloads caused substantial latency and throughput degradation despite zero HTTP errors.

## 5. Instance-size experiment

The endpoint currently uses `Standard_DS2_v2` with one instance.

A previous instance-size experiment compared `Standard_DS1_v2` and `Standard_DS2_v2` at 1 VU:

| Instance | Throughput (req/s) | p50 (ms) | p95 (ms) | p99 (ms) | Errors |
|---|---:|---:|---:|---:|---:|
| DS1_v2 | 7.4818 | 126.4 | 163.8 | 194.5 | 0% |
| DS2_v2 | 6.6715 | 131.7 | 215.5 | 341.0 | 0% |

This comparison was performed before the authenticated load-test series documented in Section 2. It is retained as historical instance-size evidence and is not used as the primary latency baseline for the current endpoint measurements.

The DS2_v2 cost value currently used by the project is 11.1955 THB/hour. This remains an estimate pending region-specific pricing verification.

## 6. Canary and rollback

A second registered model, version `3`, was deployed as `green` while version `2` remained `blue`. The canary used a 90/10 traffic split.

- 90/10 traffic was verified at **2026-09-21T06:26:33Z**.
- Aggregate blinded canary measurement: p50 135.7 ms, p95 271.0 ms, p99 523.0 ms, 0% errors.
- Rollback began at **2026-09-21T06:30:03Z**.
- Final traffic was verified as `blue=100`, `green=0`.

The degradation was detected from aggregate latency metrics without using model-version identity to make the decision.

The current DS2_v2 baseline (1 VU) produced a p95 of 233.0 ms. The canary aggregate p95 of 271.0 ms exceeded the pre-declared 200 ms target, confirming degradation. The rollback was executed and verified as `blue=100`, `green=0`.

## 7. Cost per 1,000 predictions

The project currently uses the following cost model:

`cost = hourly_rate × (1000 / (throughput × utilisation)) / 3600`

The DS2_v2 starting rate in `src/costs.py` is **11.1955 THB/hour**. This is currently treated as a pricing estimate rather than an Azure billing statement.

The existing cost calculation was based on the previous DS2_v2 throughput measurement of **6.671472 predictions/s**.

| Assumed utilisation | THB / 1,000 predictions |
|---:|---:|
| 5% | 9.3229 |
| 25% | 1.8646 |
| 80% | **0.5827** |

The primary estimate uses **80% utilisation**. Utilisation is an important assumption because a warm endpoint incurs its hourly compute cost even when request volume is low.

The existing batch break-even calculation uses the project's assumption of one scheduled batch run per day costing 50% of one endpoint-hour. This calculation should be revisited so that the batch cost comparison is based on the measured batch throughput and explicitly stated batch-job assumptions.

## 8. Teardown

The Lab 3 endpoint was explicitly deleted after testing and subsequently verified with Azure CLI as `ResourceNotFound`.

The repository `make teardown` target was corrected to use Lab 3 tags and to delete tagged online endpoints.

## 9. Validation

Final project test suite:

```text
34 passed, 1 warning