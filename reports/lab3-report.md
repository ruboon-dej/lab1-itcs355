# Lab 3 — Serving, Load Testing, Canary/Rollback, and Cost

## 1. Service validation

The FastAPI service provides `/predict`, `/predict/batch`, `/health`, and `/ready`. The model is loaded once during application startup, and responses include the deployed model version. Structured request logging records request ID, latency, and model version.

Final test result: `34 passed, 1 warning`.

## 2. Load testing

The k6 test used a pre-declared p95 latency target of less than 200 ms.

| VUs | Throughput | p50 | p95 | Errors |
|---:|---:|---:|---:|---:|
| 1 | 7.48 req/s | 126.4 ms | 163.8 ms | 0% |
| 10 | 54.08 req/s | 147.6 ms | 292.5 ms | 74.7% |
| 50 | 303.94 req/s | 136.8 ms | 263.4 ms | 96.19% |

## 3. Batch, payload, and instance findings

A batch of 100 processed approximately 594.96 predictions/s with zero errors. Batch p95 was 265.8 ms.

Payload testing showed increasing latency:

| Payload | p50 | p95 | p99 | Errors |
|---:|---:|---:|---:|---:|
| 1 KB | 124.6 ms | 164.2 ms | 220.2 ms | 0% |
| 10 KB | 129.8 ms | 212.2 ms | 266.9 ms | 0% |
| 100 KB | 941.4 ms | 2029.3 ms | 2349.3 ms | 0% |
| 500 KB | 521.9 ms | 1384.1 ms | 1578.7 ms | 0% |

Instance-size results:

| Instance | Throughput | p50 | p95 | p99 | Errors |
|---|---:|---:|---:|---:|---:|
| DS1_v2 | 7.48 req/s | 126.4 ms | 163.8 ms | 194.5 ms | 0% |
| DS2_v2 | 6.67 req/s | 131.7 ms | 215.5 ms | 341.0 ms | 0% |

The DS2_v2 measurement did not improve the observed performance.

## 4. Canary and rollback

The production model was version 2 and the canary was version 3. Traffic was initially split 90/10.

Using aggregate metrics without relying on model-version identity, baseline p95 was 163.8 ms and the blinded canary measurement produced p95 of 271.0 ms with 0% errors. This was an increase of approximately 107.2 ms and crossed the pre-declared 200 ms target.

Canary traffic was recorded at 90/10 at `2026-09-21T06:26:33Z`. Detection took approximately 60 seconds based on the 60-second observation window. Rollback began at `2026-09-21T06:30:03Z`. Final Azure verification showed `blue=100`, `green=0`.

A shorter monitoring window or continuous p95 alerting could reduce detection time. A 50/50 split would expose twice as much traffic to the canary compared with 90/10; the exact metric effect would require measurement.

## 5. Cost per 1,000 predictions

Measured Standard_DS2_v2 throughput: 6.671472 predictions/s.

Formula:

`hourly_rate × (1000 / (throughput × utilisation)) / 3600`

The DS2_v2 rate used was 11.1955 THB/hour. This is a pricing-based estimate, not an Azure billing statement.

| Utilisation | THB / 1,000 predictions |
|---:|---:|
| 5% | 9.3229 |
| 25% | 1.8646 |
| 80% | 0.5827 |

Using the project's batch-cost assumption of one scheduled batch run per day at 50% of one endpoint-hour, the break-even point is approximately 0.003045 req/s, or 263 requests/day.

## 6. Teardown

The Azure ML online endpoint was explicitly deleted after testing. A subsequent Azure CLI lookup returned `ResourceNotFound`, confirming that the endpoint no longer exists.

## 7. Validation

Final project validation:

`34 passed, 1 warning`

Python compilation of `cloudlayer/azure.py` also completed successfully.
