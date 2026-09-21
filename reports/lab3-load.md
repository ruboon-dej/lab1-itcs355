# ITCS355 Lab 3 — Serving, Load Testing, and Rollback

## 1. Serving configuration

- Provider: Azure ML
- Region: Japan East
- Endpoint: `itcs355-itcs355-6688022-predict`
- Serving image: `itcs355-serve:11c521f`
- Production model: registry `itcs355-6688022`, version `2`
- Serving instance: `Standard_DS2_v2`, 1 instance
- Model version is returned in every prediction response and `X-Model-Version` response header.
- `/health` is the liveness route; `/ready` checks model readiness; `/predict` is the scoring route.

## 2. Latency target and concurrency

The p95 target was declared **before measurement** as **<200 ms**. Measurements used a 60-second k6 run and the same single prediction payload.

| VUs | Requests | Throughput (req/s) | p50 (ms) | p95 (ms) | p99 (ms) | Error rate |
|---:|---:|---:|---:|---:|---:|---:|
| 1 | 449 | 7.4818 | 126.4 | 163.8 | 194.5 | 0.00% |
| 10 | 3,254 | 54.0823 | 147.6 | 292.5 | — | 74.70% |
| 50 | 18,549 | 303.9426 | 136.8 | 263.4 | — | 96.19% |

The endpoint meets the stated p95 target at **1 VU** with zero errors. The first tested concurrency that does not meet the target is **10 VUs**, where both p95 and the error rate degrade substantially. The observed breaking point is therefore between 1 and 10 VUs under this configuration.

The 10- and 50-VU runs produced many Azure ingress/transport `INTERNAL_ERROR` responses. The service logs also showed successful 200 responses, so these failures should not be interpreted as application-level schema/model failures without additional provider-side evidence.

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

Batching therefore processed far more predictions per second, although the p95 of the batch request itself exceeded the pre-declared 200 ms request-latency target.

## 4. Payload-size experiment

At 1 VU, request JSON was inflated with legal JSON whitespace while keeping the prediction content unchanged.

| Payload | Requests | p50 (ms) | p95 (ms) | p99 (ms) | Error rate | Throughput (req/s) |
|---:|---:|---:|---:|---:|---:|---:|
| 1 KB | 444 | 124.6 | 164.2 | 220.2 | 0% | 7.40 |
| 10 KB | 426 | 129.8 | 212.2 | 266.9 | 0% | 7.09 |
| 100 KB | 53 | 941.4 | 2,029.3 | 2,349.3 | 0% | 0.88 |
| 500 KB | 87 | 521.9 | 1,384.1 | 1,578.7 | 0% | 1.43 |

The 1 KB payload met the p95 target. At 10 KB the p95 slightly exceeded the target, and 100 KB caused a sharp latency/throughput degradation despite zero HTTP errors.

## 5. Instance-size experiment

The same 1-VU, 60-second measurement was run on `Standard_DS1_v2` and `Standard_DS2_v2`.

| Instance | Throughput (req/s) | p50 (ms) | p95 (ms) | p99 (ms) | Errors |
|---|---:|---:|---:|---:|---:|
| DS1_v2 | 7.4818 | 126.4 | 163.8 | 194.5 | 0% |
| DS2_v2 | 6.6715 | 131.7 | 215.5 | 341.0 | 0% |

DS2_v2 did not improve the measured 1-VU latency or throughput. The DS2 cost used for the serving estimate is 11.1955 THB/hour.

## 6. Canary and rollback

A second registered model, version `3`, was deployed as `green` while version `2` remained `blue`. The canary used a 90/10 traffic split.

- 90/10 traffic was verified at **2026-09-21T06:26:33Z**.
- Aggregate blinded canary measurement: p50 135.7 ms, p95 271.0 ms, p99 523.0 ms, 0% errors.
- Baseline p95 was 163.8 ms; the canary p95 increased by approximately 107.2 ms and crossed the pre-declared 200 ms target.
- Detection time was approximately **60 seconds**, corresponding to the 60-second observation window.
- Rollback began at **2026-09-21T06:30:03Z**.
- Final traffic was verified as `blue=100`, `green=0`.

The degradation was detected from aggregate latency metrics without using model-version identity to make the decision. A shorter observation window or continuous alerting against the p95 threshold could reduce detection time. A 50/50 split would expose twice as much traffic to the canary compared with 90/10; the exact metric effect would require measurement.

## 7. Cost per 1,000 predictions

The calculation uses the measured DS2_v2 throughput of **6.671472 predictions/s**:

`cost = hourly_rate × (1000 / (throughput × utilisation)) / 3600`

The DS2_v2 starting rate used in `src/costs.py` is **11.1955 THB/hour**, based on the pricing reference and the stated THB/USD conversion assumption. This is an estimate, not an Azure billing statement.

| Assumed utilisation | THB / 1,000 predictions |
|---:|---:|
| 5% | 9.3229 |
| 25% | 1.8646 |
| 80% | **0.5827** |

The primary estimate uses **80% utilisation**. Utilisation is the most fragile assumption because a warm endpoint incurs its hourly cost even when request volume is low.

Using the project's batch assumption of one scheduled batch run per day costing 50% of one endpoint-hour (5.5977 THB/run), the calculated break-even is **0.003045 req/s**, approximately **263 requests/day**. Below that request volume, scheduled batch inference is cheaper under these assumptions.

## 8. Teardown

The Lab 3 endpoint was explicitly deleted after testing and subsequently verified with Azure CLI as `ResourceNotFound`. The repository `make teardown` target was corrected to use Lab 3 tags and to delete tagged online endpoints.

## 9. Validation

Final project test suite:

```text
34 passed, 1 warning
