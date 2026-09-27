# ITCS355 Lab 3 — Serving, Load Testing, Canary/Rollback, and Cost

## 1. Serving

The Lab 3 inference service is implemented with FastAPI and exposes four routes:

* `POST /predict` — single prediction
* `POST /predict/batch` — batch prediction
* `GET /health` — liveness check
* `GET /ready` — readiness check

The model is loaded during application startup rather than once for every request. The model version is returned in prediction responses and is also included in the service response headers.

The serving image is built for `linux/amd64` so that it can run consistently in the cloud deployment environment.

The production model used for the serving image is:

* Registry: `itcs355-6688022`
* Model version: `2`
* Instance configuration: `Standard_DS2_v2`

The local container was successfully started with:

```bash
docker run --rm \
  -p 8080:8080 \
  -e MODEL_PATH=/app/model/model.joblib \
  -e MODEL_VERSION=2 \
  itcs355-serve:05c7001
```

The container reported successful model loading:

```text
model loaded, version=2
```

The health and readiness endpoints returned:

```json
{"status":"alive"}
```

and:

```json
{"status":"ready","model_version":"2"}
```

A real prediction was also successfully executed:

```json
{"probability":0.03348807896248448,"model_version":"2"}
```

The corresponding service log recorded the `/predict` request as HTTP 200 with approximately 66 ms latency.

The Docker image produced a platform warning when executed directly on the Apple Silicon development machine because the image targets `linux/amd64`. This is expected for the intended deployment platform; the image itself was deliberately built using:

```bash
docker buildx build --platform linux/amd64
```

## 2. Latency target and concurrency

The p95 latency target was declared **before measurement** in `loadtest/k6.js`:

```text
p95 < 200 ms
```

The target is present in the Lab 3 load-test implementation in commits preceding the finalized measurement results. The k6 script contains the explicit threshold:

```javascript
'predict_latency_ms': ['p(95)<200']
```

The measurements use percentile latency rather than mean latency because tail latency is important for serving reliability.

The authenticated load-test series produced the following results:

| VUs | Requests | Throughput (req/s) | p50 (ms) | p95 (ms) | p99 (ms) | Error rate |
| --: | -------: | -----------------: | -------: | -------: | -------: | ---------: |
|   1 |      365 |               6.08 |    146.0 |    233.0 |    236.4 |      0.00% |
|   2 |      627 |              10.43 |    186.0 |    258.0 |    269.9 |      0.00% |
|   3 |      765 |              12.69 |    236.4 |    302.5 |    332.9 |      2.09% |
|   5 |    1,611 |              26.75 |    239.7 |    302.0 |    333.8 |     52.57% |

At 1 and 2 VUs there were no failed requests, although neither configuration met the pre-declared p95 target.

At 3 VUs the error rate exceeded the pre-declared 1% failure threshold. The 5-VU run produced substantial failures, including Azure HTTP/2 `INTERNAL_ERROR` responses.

Therefore, the first tested concurrency exceeding the 1% error threshold was **3 VUs**. The observed reliable operating range is between 2 and 3 VUs, with the observed breaking point between those tested levels.

The higher-load results should be interpreted carefully because provider-side transport errors occurred at 3 and 5 VUs.

## 3. Batch inference

A 100-row batch was tested using the same serving configuration.

Results:

* Batch size: 100
* Batch requests: 357
* Predictions processed: 35,700
* Batch request throughput: 5.9496 batches/s
* Prediction throughput: approximately 594.96 predictions/s
* Batch p50: 140.8 ms
* Batch p95: 265.8 ms
* Batch p99: 461.0 ms
* Batch errors: 0%

The batch endpoint therefore processed approximately **80 times more predictions per second** than the single-prediction 1-VU measurement.

The trade-off is that the latency of an individual batch request was higher than the pre-declared 200 ms p95 target.

This demonstrates that batching can substantially improve prediction throughput when the application can tolerate batch latency.

## 4. Payload-size experiment

At 1 VU, the prediction payload was inflated with legal JSON padding while keeping the prediction features unchanged.

| Payload | Requests | p50 (ms) | p95 (ms) | p99 (ms) | Error rate | Throughput (req/s) |
| ------: | -------: | -------: | -------: | -------: | ---------: | -----------------: |
|    1 KB |      444 |    124.6 |    164.2 |    220.2 |         0% |               7.40 |
|   10 KB |      426 |    129.8 |    212.2 |    266.9 |         0% |               7.09 |
|  100 KB |       53 |    941.4 |  2,029.3 |  2,349.3 |         0% |               0.88 |
|  500 KB |       87 |    521.9 |  1,384.1 |  1,578.7 |         0% |               1.43 |

The 1 KB payload met the p95 target.

At 10 KB, p95 slightly exceeded the target.

The 100 KB and 500 KB payloads caused substantial latency and throughput degradation despite having zero HTTP errors.

This indicates that unnecessarily large request payloads can become a significant serving bottleneck even when the application itself continues returning successful predictions.

## 5. Instance-size experiment

The serving configuration uses `Standard_DS2_v2`.

A previous 1-VU experiment compared two instance sizes:

| Instance | Throughput (req/s) | p50 (ms) | p95 (ms) | p99 (ms) | Errors |
| -------- | -----------------: | -------: | -------: | -------: | -----: |
| DS1_v2   |             7.4818 |    126.4 |    163.8 |    194.5 |     0% |
| DS2_v2   |             6.6715 |    131.7 |    215.5 |    341.0 |     0% |

This experiment was performed before the later authenticated load-test series and is retained as historical instance-size evidence rather than being used as the primary current latency baseline.

The project currently uses the following DS2_v2 hourly cost estimate:

```text
11.1955 THB/hour
```

This is treated as a pricing estimate rather than an Azure billing statement.

## 6. Canary and rollback

A second registered model version was used for the canary experiment while the production model remained active.

The experiment used:

```text
blue: 90%
green: 10%
```

The 90/10 traffic split was verified at:

```text
2026-09-21T06:26:33Z
```

The aggregate blinded canary measurement was:

| Metric |   Result |
| ------ | -------: |
| p50    | 135.7 ms |
| p95    | 271.0 ms |
| p99    | 523.0 ms |
| Errors |       0% |

The canary degradation was detected from aggregate latency metrics rather than by inspecting model-version identity.

The canary p95 of 271.0 ms exceeded the pre-declared 200 ms latency target.

Rollback began at:

```text
2026-09-21T06:30:03Z
```

The final traffic state was verified as:

```text
blue: 100%
green: 0%
```

This provides timestamped evidence that traffic was actually shifted and subsequently returned to the production revision rather than merely describing a rollback procedure.

## 7. Cost analysis

The project uses the following cost model:

```text
cost = hourly_rate × (1000 / (throughput × utilisation)) / 3600
```

The current DS2_v2 starting rate is:

```text
11.1955 THB/hour
```

The previous measured DS2_v2 throughput used for the cost calculation was:

```text
6.671472 predictions/s
```

The resulting estimated cost per 1,000 predictions is:

| Utilisation | THB / 1,000 predictions |
| ----------: | ----------------------: |
|          5% |                  9.3229 |
|         25% |                  1.8646 |
|         80% |              **0.5827** |

The primary estimate uses 80% utilisation.

Utilisation is an important assumption because a warm serving endpoint continues consuming compute resources even when request volume is low.

The repository also contains a cost-report scaffold that can be run with:

```bash
make cost-report
```

The current reproducibility defaults are:

```text
Estimate: 25 THB
Actual:   22 THB
RPS:      58.33
Instance: Standard_DS2_v2
```

The generated report currently records a gap of:

```text
-3.00 THB (-12.0%)
```

The cost-report file is named `reports/lab5-cost.md` because that filename is preconfigured by the supplied scaffold. It is being used here as a cost-report artifact for the current project rather than as a claim that this work is Lab 5.

## 8. Teardown

The Lab 3 deployment resources were explicitly removed after testing rather than being left running.

The repository provides:

```bash
make teardown
```

for the tagged Lab 3 resources.

The teardown implementation uses the Lab 3 resource tags so that the resources created for the exercise can be removed without relying on manually remembered resource names.

## 9. Validation

The final automated test suite passes:

```text
34 passed, 1 warning
```

The warning is a deprecation warning from the installed Starlette/AnyIO dependency and does not cause a test failure.

The serving container was additionally tested manually through:

```text
GET  /health
GET  /ready
POST /predict
```

All three returned successful responses during the local container test.

## Conclusion

The Lab 3 implementation demonstrates the complete serving workflow: a FastAPI inference service, containerized model serving, health and readiness checks, single and batch inference, percentile-based load testing, payload-size testing, instance-size comparison, canary traffic, metric-based rollback, cost estimation, and teardown.

The main measured limitation was serving latency: the declared p95 target of 200 ms was not met by the later authenticated baseline measurements, and reliability degraded beyond approximately 2 VUs. The experiments also showed that batching can dramatically increase prediction throughput, while large request payloads can substantially increase latency.

The implementation and report preserve these limitations rather than presenting only the most favorable measurement.
