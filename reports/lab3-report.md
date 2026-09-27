# ITCS355 Lab 3 — Serving, Load Testing, Canary/Rollback, and Cost

## 1. Serving

The Lab 3 inference service is implemented with FastAPI and exposes four routes:

* `POST /predict` — single prediction
* `POST /predict/batch` — batch prediction
* `GET /health` — liveness check
* `GET /ready` — readiness check

The model is loaded during application startup rather than once for every request. The model version is returned in prediction responses and is also included in the service response headers.

Because the Azure for Students subscription is subject to Azure ML managed-online-endpoint quota limitations, the Lab 3 deployment uses **Azure Container Apps** rather than Azure ML managed online endpoints. The Container Apps deployment is intended to support scale-to-zero and avoid consuming Azure ML managed endpoint quota.

The serving image is built for `linux/amd64` so that it can run consistently in the cloud deployment environment.

The production model used for the serving deployment is:

* Container registry: `itcs3556688022.azurecr.io`
* Model version: `2`
* Serving instance configuration: `Standard_DS2_v2`

The local serving container was successfully started with:

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

The Docker image produced a platform warning when executed directly on the Apple Silicon development machine because the image targets `linux/amd64`. This is expected for the intended cloud deployment platform. The image was deliberately built using:

```bash
docker buildx build --platform linux/amd64
```

The Container Apps deployment was successfully exercised and the serving workflow was validated independently from the Azure ML managed-online-endpoint path.

## 2. Latency target and concurrency

The p95 latency target was declared **before measurement** in `loadtest/k6.js`:

```text
p95 < 200 ms
```

The k6 script contains the explicit threshold:

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

Therefore, the first tested concurrency exceeding the 1% error threshold was **3 VUs**. The observed reliable operating range is between the tested 2-VU and 3-VU levels, with the observed breaking point between those tested levels.

The higher-load results should be interpreted carefully because provider-side transport errors occurred at 3 and 5 VUs.

## 3. Batch inference

A 100-row batch experiment was performed during the earlier Azure ML managed-online-endpoint deployment, before the final migration to Azure Container Apps.

The results are retained as historical experiment evidence and are **not used as the current Container Apps performance baseline**.

Historical results:

* Batch size: 100
* Batch requests: 357
* Predictions processed: 35,700
* Batch request throughput: 5.9496 batches/s
* Prediction throughput: approximately 594.96 predictions/s
* Batch p50: 140.8 ms
* Batch p95: 265.8 ms
* Batch p99: 461.0 ms
* Batch errors: 0%

The historical batch experiment processed approximately **80 times more predictions per second** than the historical single-prediction 1-VU measurement.

These historical results demonstrate that batching can substantially improve prediction throughput when the application can tolerate batch latency. They are not presented as a current Container Apps benchmark.

## 4. Payload-size experiment

The following payload-size experiment was performed during the earlier Azure ML managed-online-endpoint deployment, before the final migration to Azure Container Apps.

The results are retained as historical experiment evidence and are **not used as the current Container Apps performance baseline**.

At 1 VU, the prediction payload was inflated with legal JSON padding while keeping the prediction features unchanged.

| Payload | Requests | p50 (ms) | p95 (ms) | p99 (ms) | Error rate | Throughput (req/s) |
| ------: | -------: | -------: | -------: | -------: | ---------: | -----------------: |
|    1 KB |      444 |    124.6 |    164.2 |    220.2 |         0% |               7.40 |
|   10 KB |      426 |    129.8 |    212.2 |    266.9 |         0% |               7.09 |
|  100 KB |       53 |    941.4 |  2,029.3 |  2,349.3 |         0% |               0.88 |
|  500 KB |       87 |    521.9 |  1,384.1 |  1,578.7 |         0% |               1.43 |

In the historical experiment, the 1 KB payload met the p95 target.

At 10 KB, p95 slightly exceeded the target.

The 100 KB and 500 KB payloads caused substantial latency and throughput degradation despite having zero HTTP errors.

These historical results indicate that unnecessarily large request payloads can become a significant serving bottleneck even when the application continues returning successful predictions. They are not presented as current Container Apps measurements.

## 5. Instance-size experiment

The serving configuration uses `Standard_DS2_v2`.

A previous 1-VU experiment compared two instance sizes:

| Instance | Throughput (req/s) | p50 (ms) | p95 (ms) | p99 (ms) | Errors |
| -------- | -----------------: | -------: | -------: | -------: | -----: |
| DS1_v2   |             7.4818 |    126.4 |    163.8 |    194.5 |     0% |
| DS2_v2   |             6.6715 |    131.7 |    215.5 |    341.0 |     0% |

This experiment was performed before the later authenticated load-test series and is retained as historical instance-size evidence rather than being used as the primary current latency baseline.

The DS2_v2 hourly value of approximately:

```text
11.1955 THB/hour
```

is treated as a pricing estimate rather than an Azure billing statement. It is not presented as an actual Container Apps billing rate.

## 6. Canary and rollback

The Lab 3 canary exercise was intended to deploy a second registered model version and route a controlled percentage of endpoint traffic to it while keeping the production revision active.

The intended configuration was:

```text
blue: 90%
green: 10%
```

However, a **true concurrent 90/10 traffic split could not be reliably implemented in the Azure Container Apps environment used for this Lab 3 deployment**.

During deployment, the Container Apps environment reported the following platform limitation:

```text
ExpressEnvironmentFeatureNotSupported
```

The deployment adapter therefore could not establish the required Container Apps revision/registry configuration needed for the intended concurrent canary workflow.

This prevented the required concurrent 90/10 revision traffic split from being established reliably in the final Container Apps environment.

This is an Azure Container Apps environment/platform limitation rather than a failure of the FastAPI application or the model itself.

Therefore, the Lab 3 submission does **not** claim that a genuine concurrent 90/10 canary was successfully implemented in the final Container Apps environment.

The rollback mechanism itself was implemented so that, when multiple revisions are available, traffic can be returned to the production revision using the Container Apps traffic-routing interface.

The repository contains the canary/rollback helper:

```text
scripts/canary_roll.py
```

The intended rollback state is:

```text
blue: 100%
green: 0%
```

The important limitation is that the 90/10 concurrent traffic experiment could not be completed reliably in the deployed Container Apps environment, so no unsupported claim is made that the final environment successfully routed exactly 10% of live traffic to a second revision.

## 7. Cost analysis

The project uses the following cost model for the serving estimate:

```text
cost = hourly_rate × (1000 / (throughput × utilisation)) / 3600
```

The DS2_v2 reference rate used by the project is:

```text
11.1955 THB/hour
```

This is a **reference pricing estimate**, not an Azure billing statement for the Container Apps deployment.

The later authenticated 1-VU measurement produced:

```text
6.08 req/s
```

Using this measured request throughput as the workload reference gives the following illustrative cost estimates:

| Utilisation | THB / 1,000 requests |
| ----------: | -------------------: |
|          5% |                10.23 |
|         25% |                 2.05 |
|         80% |                 0.64 |

These values should be interpreted as a sensitivity analysis rather than actual Container Apps charges because the reference hourly rate is based on the DS2_v2 pricing assumption.

The Container Apps deployment is also designed to support scale-to-zero. Therefore, actual cost depends on the amount of time the service is actively running rather than simply assuming a continuously warm DS2_v2 instance.

The repository also contains:

```text
reports/lab5-cost.md
```

This file is retained as supporting cost information from the supplied project material. Its placeholder billing values are not used as evidence for the Lab 3 serving-cost calculation.

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

The Lab 3 implementation demonstrates the serving workflow using a provider-independent FastAPI service deployed through Azure Container Apps, including model loading, health and readiness checks, single and batch inference, percentile-based load testing, payload-size testing, rollback support, cost estimation, and teardown.

The current authenticated load tests showed that the pre-declared p95 target of 200 ms was not met even at the lowest tested concurrency, while reliability degraded beyond approximately 2 VUs. The experiments also show that batching can substantially increase prediction throughput, while large request payloads can substantially increase latency.

The batch and payload-size results are explicitly identified as **historical Azure ML measurements from before the migration to Azure Container Apps**. They are retained as experiment evidence but are not presented as current Container Apps performance measurements.

The intended concurrent 90/10 canary traffic experiment could not be completed in the final Azure Container Apps environment because the required revision/traffic configuration was not supported by the Container Apps environment. The deployment logs recorded the relevant platform limitation as `ExpressEnvironmentFeatureNotSupported`.

This limitation is documented explicitly rather than presenting an unsupported 90/10 traffic split as successful evidence.

The final automated validation passes with:

```text
34 passed, 1 warning
```
