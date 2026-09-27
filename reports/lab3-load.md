# ITCS355 Lab 3 — Serving, Load Testing, and Rollback

## 1. Serving configuration

- Provider: Azure Container Apps
- Region: Japan East
- Endpoint: `itcs355-itcs355-6688022-predict`
- Serving image: `itcs355-serve:05c7001`
- Production model: container registry `itcs3556688022.azurecr.io`, model version `2`
- Serving instance configuration: `Standard_DS2_v2`
- Model version is returned in every prediction response and `X-Model-Version` response header.
- `/health` is the liveness route.
- `/ready` checks model readiness.
- `/predict` is the single-prediction scoring route.
- `/predict/batch` is the batch-prediction scoring route.

Because the Azure for Students subscription is subject to Azure ML managed-online-endpoint quota limitations, the final Lab 3 deployment uses Azure Container Apps rather than an Azure ML managed online endpoint. This avoids relying on Azure ML managed online endpoint quota and supports the intended scale-to-zero deployment model.

The serving image is built for `linux/amd64` so that it can run consistently in the cloud deployment environment.

## 2. Latency target and concurrency

The p95 latency target was declared **before measurement** as:

```text
p95 < 200 ms
```

The k6 implementation contains the explicit threshold:

```javascript
'predict_latency_ms': ['p(95)<200']
```

Measurements used 60-second k6 runs against the deployed serving endpoint with the same single-prediction payload.

| VUs | Requests | Throughput (req/s) | p50 (ms) | p95 (ms) | p99 (ms) | Error rate |
| --: | -------: | -----------------: | -------: | -------: | -------: | ---------: |
|   1 |      365 |               6.08 |    146.0 |    233.0 |    236.4 |      0.00% |
|   2 |      627 |              10.43 |    186.0 |    258.0 |    269.9 |      0.00% |
|   3 |      765 |              12.69 |    236.4 |    302.5 |    332.9 |      2.09% |
|   5 |    1,611 |              26.75 |    239.7 |    302.0 |    333.8 |     52.57% |

At 1 and 2 VUs there were no failed requests, although neither configuration met the pre-declared p95 target.

At 3 VUs, the error rate exceeded the pre-declared 1% failure threshold. The 5-VU run produced substantial failures, including Azure HTTP/2 `INTERNAL_ERROR` responses.

Therefore, the first tested concurrency exceeding the 1% error threshold was **3 VUs**.

The observed reliable operating range was between the tested 2-VU and 3-VU levels, with the observed breaking point between those tested levels.

The 3- and 5-VU results should be interpreted carefully because provider-side transport errors occurred at those loads.

## 3. Batch inference

A 100-row batch was tested using the same serving configuration.

* Batch size: 100
* Batch requests: 357
* Predictions processed: 35,700
* Batch request throughput: 5.9496 batches/s
* Prediction throughput: approximately 594.96 predictions/s
* Batch p50: 140.8 ms
* Batch p95: 265.8 ms
* Batch p99: 461.0 ms
* Batch errors: 0%

Batching therefore processed approximately **80 times more predictions per second** than the single-prediction 1-VU measurement.

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

The 100 KB and 500 KB payloads caused substantial latency and throughput degradation despite zero HTTP errors.

This indicates that unnecessarily large request payloads can become a significant serving bottleneck even when the application continues returning successful predictions.

## 5. Instance-size experiment

The current serving configuration uses `Standard_DS2_v2`.

A previous 1-VU experiment compared two instance sizes:

| Instance | Throughput (req/s) | p50 (ms) | p95 (ms) | p99 (ms) | Errors |
| -------- | -----------------: | -------: | -------: | -------: | -----: |
| DS1_v2   |             7.4818 |    126.4 |    163.8 |    194.5 |     0% |
| DS2_v2   |             6.6715 |    131.7 |    215.5 |    341.0 |     0% |

This comparison was performed before the later authenticated load-test series documented in Section 2.

It is retained as historical instance-size evidence and is not used as the primary latency baseline for the current endpoint measurements.

The DS2_v2 value of approximately `11.1955 THB/hour` is treated as a reference pricing estimate rather than an Azure billing statement.

## 6. Canary and rollback

The original Lab 3 exercise intended to deploy a second registered model version and route a controlled percentage of endpoint traffic to it while keeping the production revision active.

The intended traffic configuration was:

```text
blue: 90%
green: 10%
```

However, a **true concurrent 90/10 traffic split could not be reliably implemented in the Azure Container Apps environment used for the final Lab 3 deployment**.

During deployment, the Container Apps environment reported the following platform limitation:

```text
ExpressEnvironmentFeatureNotSupported
```

The deployment adapter therefore could not establish the required Container Apps revision/registry configuration needed for the intended concurrent canary workflow.

The deployment logs also showed:

```text
[attempt 1] generic --set update exit 0
ACR registry auth attempt 1 didn't stick (registries still not wired) -- retrying...
```

The same registry-wiring condition occurred on the second attempt:

```text
ACR registry auth attempt 2 didn't stick (registries still not wired) -- retrying...
```

Although the CLI update command returned exit code 0, the expected registry/revision configuration was not actually present afterward. The adapter therefore retried the configuration rather than treating the operation as successfully established.

This prevented the required concurrent 90/10 revision traffic split from being established reliably in the final Container Apps environment.

This is an Azure Container Apps environment/platform limitation rather than a failure of the FastAPI application or the model itself.

Therefore, this report does **not** claim that a genuine concurrent 90/10 canary was successfully implemented.

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

The important limitation is that the 90/10 concurrent traffic experiment could not be completed reliably in the deployed Container Apps environment, so no unsupported claim is made that exactly 10% of live traffic was routed to a second revision.

## 7. Cost per 1,000 requests

The project uses the following reference cost model:

```text
cost = hourly_rate × (1000 / (throughput × utilisation)) / 3600
```

The DS2_v2 reference rate used by the project is:

```text
11.1955 THB/hour
```

This is a reference pricing estimate, not an Azure billing statement for the Container Apps deployment.

The later authenticated 1-VU load test measured:

```text
6.08 requests/s
```

Using this measured request throughput with the reference hourly rate gives the following illustrative sensitivity analysis:

| Utilisation | THB / 1,000 requests |
| ----------: | -------------------: |
|          5% |                10.23 |
|         25% |                 2.05 |
|         80% |                 0.64 |

These values are estimates only. They should not be interpreted as actual Azure Container Apps charges because the hourly rate is based on the project's `Standard_DS2_v2` reference pricing rather than a verified Container Apps billing meter.

The Container Apps deployment is intended to support scale-to-zero. Therefore, actual serving cost depends on how long the service is actively running and the actual Container Apps billing model rather than simply assuming a continuously warm DS2_v2 instance.

## 8. Teardown

The Lab 3 deployment resources were explicitly removed after testing rather than being left running.

The repository provides:

```bash
make teardown
```

for the tagged Lab 3 resources.

The teardown implementation uses the Lab 3 resource tags so that resources created for the exercise can be removed without relying on manually remembered resource names.

## 9. Validation

Final automated test suite:

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

The load tests showed that the pre-declared p95 target of 200 ms was not met even at the lowest tested concurrency, while reliability degraded beyond approximately 2 VUs. The experiments also showed that batching can dramatically increase prediction throughput, while large request payloads can substantially increase latency.

The intended concurrent 90/10 canary traffic experiment could not be completed in the final Azure Container Apps environment because the required revision/traffic configuration was not supported by the Container Apps environment. The deployment logs recorded the relevant platform limitation as `ExpressEnvironmentFeatureNotSupported` and showed that the expected registry/revision wiring did not persist after the traffic/update operation.

This limitation is documented explicitly rather than presenting an unsupported 90/10 traffic split as successful evidence.

The final automated validation passes with:

```text
34 passed, 1 warning
```

```

This version also keeps the **load-test evidence**, **canary limitation**, and **cost assumptions** internally consistent with the `lab3-report.md` and `lab5-cost.md` versions we just settled on.
```
