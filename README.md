# ITCS355 Lab 1 — Reproducible Training

> **Course materials live in [`course/`](course/README.md)** — syllabus, slides, the faculty
> specification, all five lab handouts, and the project brief. Every document is Markdown and
> renders on GitHub, diagrams included. New to the repo? Start with the
> [portability reference](course/reference/cloud-portability-reference.md).
> Keep this block when you edit the rest of this file; it is not part of the Lab 1 deliverable.

Predicting machine failure within 7 days from sensor readings. The model is not the point;
whether a stranger can reproduce it is.

> **This README is graded.** A grader with Docker and nothing else from your setup runs one
> command and compares the result against the claim below. Edit every `<...>` and delete the
> instruction blocks marked **REPLACE** before submitting.

---

## Reproduce

```bash
make reproduce
```

expected test_roc_auc: 0.8493 ± 0.0075

Runtime: about 40 seconds on 4 cores. No cloud account or credentials needed for this command —
that is deliberate, and it is why a grader can run it.

---

## The problem

240 machines, 25 readings each, 6 sensor features, binary target `failed_within_7d` with a
positive rate near 12%.

Machines have persistent characteristics — a hot-running machine reads hot in every row. So the
train/validation/test split is **grouped by `machine_id`**: every reading from one machine lands
in exactly one partition. Splitting row-wise instead lets the model memorise the machine and
reports a validation score that will never survive production. `tests/test_data.py` asserts this
property holds, and Lab 4 turns it into a CI gate.

Bringing your own dataset is allowed. Replace `scripts/make_dataset.py`, update the schema in
`src/data.py`, and keep every test passing.

---

## Layout

```
src/          Layer 1 — provider-neutral. No SDKs, no bucket names, no absolute paths.
cloudlayer/   Layer 3 — the only place a provider SDK may be imported.
scripts/      Dataset generation, cloud check, portability audit, metric verification.
tests/        Data contract tests and split property tests.
```

`src/config.py` is the single point of environment knowledge. Everything else reads from it.
`make portability-audit` enforces the rule; it fails the build if a provider string appears in
`src/` or `tests/`.

---

## Setup

```bash
cp cloud.env.example cloud.env      # fill in, never commit
make setup
make cloud-check                    # eight slots, all PASS
make data                           # generate the dataset
make test                           # 10 tests, all passing
```

Post your `make cloud-check` output in the course channel before Session 1.

---

## What you must finish

Four `TODO` markers are left in the repo deliberately. Each is a graded decision, not busywork.

| Where | What |
|---|---|
| `requirements.txt` | Regenerate with `pip-compile --generate-hashes` |
| `Dockerfile` | Pin the base image by digest; add `--require-hashes` |
| `cloudlayer/<your provider>.py` | Implement `upload`, `download`, `push_image` |
| This README | The reproducibility trade-off question below |

Then:

```bash
make image-push        # image reaches your registry, digest-pinned
dvc init && dvc remote add -d storage ${BLOB_URI}/dvc
dvc add data/raw && dvc push
```

Run five or more tracked runs varying something meaningful — not five identical runs with
different seeds.

---

## Reproducibility trade-off

First of all, I would get rid of the hashed dependencies. Whenever you try to recreate or run the thing again, the use of digest pinned base images and controlled seeds will be
immediately seen as faulty since both a moved tag and an unset seed will appear right away. On the other hand, the absence of hashes does not make itself immediately
apparent in this way; if you republish your wheel with the same version number, your build process will be altered in some quiet way and this will only become noticeable later.

Three things pin your build: hashed dependencies, a digest-pinned base image, and controlled
seeds. Under real time pressure you would keep some and drop others.

Which would you drop first, and what specifically breaks when you do? There is a defensible
answer, and we compare answers in Session 2. An answer that refuses to choose scores zero.

---

## Notes for the grader

requirements.txt was regenerated with pip-compile --generate-hashes; one transitive dependency (greenlet) required an explicit entry in requirements.in since --require-hashes rejects
unpinned transitive packages.
**DVC remote access:** Raw data is versioned in a private Azure Blob Storage container (`itcs355` on account `itcs3556688022`) and requires Azure credentials with
`Storage Blob Data Reader` access to pull via `dvc pull`. This is **not required to reproduce the graded metric** — `make reproduce` regenerates the raw dataset deterministically
from the fixed seed via `scripts/make_dataset.py`, with no dependency on DVC or cloud access.

---

## Checklist before you submit

- [ ] `make reproduce` works from a fresh clone, on a machine that is not yours
- [ ] `make verify` passes against your claim line
- [ ] `make test` — all tests pass
- [ ] `make portability-audit` — clean
- [ ] Image builds for `linux/amd64` and is pushed, digest-pinned
- [ ] `dvc push` completed; a grader can `dvc pull`
- [ ] Five or more tracked runs with params, metrics, data fingerprint, and commit SHA
- [ ] Every **REPLACE** block above is gone (the course-materials block at the top stays)
- [ ] `git log -p | grep -i -E "secret|password|AKIA|BEGIN PRIVATE"` returns nothing

That last check is not optional. A credential in Git history is an automatic deduction in this
course, and rotating it is your responsibility, not the grader's.

---

## Lab 2 — Cloud Training, Model Selection, Registry, and Reproducible Deployment

### Cloud training

The Lab 2 implementation was prepared for Azure ML managed compute using
discounted LowPriority compute. The intended compute was `Standard_DS3_v2`
with `low_priority` tier.

The workspace could not provision the required compute under the available
Azure for Students subscription. The `lab2-lowpri` compute failed with
`ClusterMinNodesExceedCoreQuota`. Azure reported that the subscription had
0 vCPUs available to Azure ML managed compute.

To verify that the failure was not specific to the DS3_v2 instance size, a
second LowPriority compute using `Standard_D2s_v3` (2 vCPUs) was also created.
It failed with the same `ClusterMinNodesExceedCoreQuota` error, reporting that
the subscription's total vCPU quota was 0.

The Azure Portal also rejected a quota-increase request because the current
subscription is not eligible for a quota increase without upgrading to
Pay-As-You-Go. I did not upgrade the subscription because this would introduce
a billing requirement unrelated to the lab.

Therefore, the remaining cloud-training work is blocked by the subscription's
Azure ML compute quota rather than by the training implementation.

Evidence:

- `lab2-lowpri` — `Standard_DS3_v2`, LowPriority — provisioning failed with
  `ClusterMinNodesExceedCoreQuota`.
- `lab2-lowpri-d2` — `Standard_D2s_v3`, LowPriority — provisioning failed with
  `ClusterMinNodesExceedCoreQuota`.
- Azure CLI reported `lowPriorityCores` quota of 3 for the region, but Azure ML
  managed compute reported a total vCPU quota of 0.
- Azure Portal quota request was rejected because the Azure for Students
  subscription is not eligible for a quota increase.
- Quota-request trace ID:
  `048fc0e0-68d6-433e-a432-42db5e788a8e`

The required discounted-compute rerun should therefore be performed in a
course-provided Azure subscription/workspace with sufficient Azure ML compute
quota if one is made available.

The 12-trial sweep and seed reruns were run on Dedicated Standard_DS3_v2 compute; the corresponding execution evidence is preserved under azure_trial_metrics/.

The current training adapter enforces LowPriority compute for new Lab 2 submissions; the historical Dedicated runs above were completed before this guard was added and are retained as experimental evidence because the required LowPriority compute could not be provisioned.

### Initial permission failure

The first remote training submission used the compute managed identity `9144aef5-...`. It already had `Storage Blob Data Contributor` on the storage account, but was missing `AcrPull` on the `itcs3556688022` container registry. The job therefore could not pull the training image. Adding `AcrPull` to the compute identity resolved this permission failure.

### Trials
The 12 actual Azure ML experiments were done on 3 hyperparameters to achieve:
`n_estimators`, `max_depth`, and `min_samples_leaf`. The total cost was roughly 2.91 THB, well within the budget of 150 THB.

### Selection
Selected config: `n_estimators=100, max_depth=4, min_samples_leaf=5`. It was
re-run across 3 seeds to check stability:

| Seed | Val ROC-AUC | Val PR-AUC | Test ROC-AUC |
|---|---|---|---|
| 20260101 | 0.8426 | 0.3932 | 0.8533 |
| 20260102 | **0.8733** | **0.4718** | 0.8463 |
| 20260103 | 0.8430 | 0.3909 | 0.8318 |

Seed 20260102 was chosen because it had the highest validation ROC-AUC of the three seed reruns, and validation performance is used for choosing the model; the test set is kept held-out. Even though seed 20260101 had a slightly better score on the test set, using the performance on the test set for choosing the model leaks information about the held-out data.

The cost of the 12 trial study was about 2.91 THB which is obviously less than the budgeted 150 THB. This is equivalent to an average of approximately 0.24 THB per trial. One monthly retrain is about 0.24 THB by that average, an estimate rather than a verified Azure bill.

One way this choice could be wrong is that the seed also reseeds
`make_dataset.py`, so the three runs vary both model randomness and the
underlying data — the observed variance does not isolate model-seed variance
alone. This same configuration scored 0.8426 in the original 12-trial sweep
(default seed), versus 0.8733 with seed 20260102 and 0.8430 with seed 20260103.
Seed-driven variation is therefore large relative to the differences observed
across the original sweep, so the sweep alone does not establish a reliably
superior configuration.

### Lineage
| Item | Value |
|---|---|
| Git commit | `6ccc5ee0e89d624811802e869f5e4099d1707776` |
| Data version | Generated dataset: `make_dataset.py --seed 20260102` |
| Data fingerprint | `3ae9705eb3f197a3` |
| MLflow run ID | `a81deea37f9b4659addf64908d518e7b` |
| Training job | `mango_boot_pbpr17lrhb` |
| Image digest | `sha256:585f50972aa5afd104c6b337fd23716a82276cb9b6a5401d7f8a0dbaf64a0d7a` |
| Seed | `20260102` |
| Val / Test ROC-AUC | `0.8733` / `0.8463` |

### Registry
Registered as `itcs355-6688022:2` with the lineage above as tags, plus
`stage=staging`. As the installed Azure ML SDK (azure-ai-ml 1.35.0) lacks a public native stage-promotion API for the workflow process, the lab staging state is expressed via the stage=staging model tag.

The registered model was trained from the seed-20260102 generated dataset,
with fingerprint 3ae9705eb3f197a3. The MLflow run a81deea37f9b4659addf64908d518e7b
is no longer available with its original container, but the Azure job
mango_boot_pbpr17lrhb and its preserved execution evidence are available under
azure_trial_metrics/.

### Promotion policy
Promotion of the ML model should be done by the ML engineer or release owner, and not all developers who are capable of training ML models. It will be the responsibility of the reviewer to demand proof of a reproducible lineage for the registered model before it is promoted, and these include: Git commit, data version, MLflow run ID, training job ID, container image digest, seed, and validation/test metrics. The selected model should have documented evaluation against the candidate configurations and a successful reload check from the model registry.

### Reload check
`reload_check.py` downloaded `itcs355-6688022:2` directly from the registry,
deserialized it, and scored 5 held-out rows — **PASS**.

**Known limitation:** `reload_check.py` splits the data with `seed=20260101`,
while the registered model was trained using data generated with
`seed=20260102`. This proves the registry-to-inference path works but is not an
exact reproduction of the original evaluation split.

To run the Azure ML registry reload check, the environment must provide
`AZURE_SUBSCRIPTION_ID`, `AZURE_RESOURCE_GROUP`, and `AZURE_ML_WORKSPACE`.

Run:

```bash
make reload-check VERSION=2
```

### Known limitations
- The local MLflow file store did not persist beyond each ephemeral container;
  Azure job logs/artifacts were used to recover completed-run metrics.
- The reload-check data split seed does not match the registered model's
  training-data seed.

### Checkpoint and interruption evidence

The remote tuning controller checkpoints study state after each trial and
skips completed trials when restarted. The checkpoint/resume behavior was
tested locally: a completed trial was recovered after restarting the
controller, and a separate running-process test was interrupted with
`Ctrl-C` while the checkpoint file remained intact. If the controller is interrupted while waiting for an Azure ML job, the submitted job is not automatically cancelled. A restart can therefore resubmit the interrupted configuration. A production controller should reconcile or cancel the in-flight job before resubmission to avoid duplicate work and cost.

The interruption evidence is preserved in
`reports/interrupt-resume-log.txt`. It records the checkpoint surviving the
local `Ctrl-C` interruption and the subsequent resume behavior. The resume test then confirmed that
the completed trial was skipped and a subsequent trial could be recorded.

An actual Azure ML LowPriority interruption could not be demonstrated because
the required LowPriority compute could not be provisioned under the available
Azure for Students quota.

---

## Lab 3 — Serving, Load Testing, Canary/Rollback, and Cost

Lab 3 covers reproducible model serving, containerisation, health and readiness checks, percentile-based load testing, batch inference, payload-size experiments, canary deployment, rollback, and serving-cost analysis.

The implementation uses **Azure Container Apps for serving** rather than Azure ML managed online endpoints. This is intentional for the Azure for Students environment and avoids depending on Azure ML managed-online-endpoint quota.

### Serving

The FastAPI service exposes four endpoints:

| Endpoint              | Purpose               |
| --------------------- | --------------------- |
| `POST /predict`       | Single prediction     |
| `POST /predict/batch` | Batch prediction      |
| `GET /health`         | Liveness check        |
| `GET /ready`          | Model readiness check |

The model is loaded during application startup rather than once per request. Prediction responses include the deployed model version.

Run the service locally with:

```bash
make serve
```

Export the model used by the local service with:

```bash
python scripts/export_model.py --out reports/model.joblib
```

Build the serving image with:

```bash
make serve-image VERSION=2
```

The serving image is explicitly built for `linux/amd64`:

```bash
docker buildx build --platform linux/amd64 ...
```

This allows the same image architecture to be used in the deployment environment when development is performed on an Apple Silicon Mac.

### Local container verification

The serving image was successfully run locally with:

```bash
docker run --rm \
  -p 8080:8080 \
  -e MODEL_PATH=/app/model/model.joblib \
  -e MODEL_VERSION=2 \
  itcs355-serve:05c7001
```

The service successfully loaded the model:

```text
model loaded, version=2
```

The health and readiness endpoints returned successful responses:

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

The Docker image targets `linux/amd64`, so Docker may report a platform warning when it is executed directly on an Apple Silicon development machine. This is expected because the deployment image was deliberately built for the target cloud architecture.

### Deployment

The repository's deployment seam is provider-adapted through `cloudlayer/`.

Build and push the serving image with:

```bash
make serve-image-push
```

Deploy the registered model with:

```bash
make deploy VERSION=2
```

Run a smoke test with:

```bash
make smoke
```

The deployment uses **Azure Container Apps** and the registered model version is used as the deployment model reference.

The provider-specific deployment details are isolated in `cloudlayer/azure.py`, while the FastAPI serving implementation remains provider-independent.

### Health versus readiness

`/health` and `/ready` intentionally represent different concepts.

`/health` answers whether the service process is alive.

`/ready` answers whether the service is ready to serve predictions, including whether the model has successfully loaded.

Therefore, a service can be alive while not yet ready. A deployment system should use readiness rather than liveness when deciding whether a new instance should receive traffic.

### Load testing

The p95 latency target was declared **before measurement**:

```text
p95 < 200 ms
```

The target is encoded directly in `loadtest/k6.js`:

```javascript
'predict_latency_ms': ['p(95)<200']
```

The load-test implementation records percentile latency rather than relying only on mean latency.

Run the standard load test with:

```bash
make loadtest TARGET=https://<endpoint>/predict
```

The k6 implementation supports concurrency, batch requests, and payload-size experiments.

Load-test evidence is preserved in:

* `reports/lab3-load.md`
* `reports/lab3-report.md`

### Concurrency results

The authenticated load-test series produced:

| VUs | Requests | Throughput (req/s) | p50 (ms) | p95 (ms) | p99 (ms) | Error rate |
| --: | -------: | -----------------: | -------: | -------: | -------: | ---------: |
|   1 |      365 |               6.08 |    146.0 |    233.0 |    236.4 |      0.00% |
|   2 |      627 |              10.43 |    186.0 |    258.0 |    269.9 |      0.00% |
|   3 |      765 |              12.69 |    236.4 |    302.5 |    332.9 |      2.09% |
|   5 |    1,611 |              26.75 |    239.7 |    302.0 |    333.8 |     52.57% |

The first tested concurrency level exceeding the 1% error threshold was **3 VUs**.

The 1- and 2-VU runs produced no failed requests, although their p95 latency was above the pre-declared 200 ms target.

At higher concurrency, reliability degraded. The 5-VU run produced substantial failures, including Azure HTTP/2 `INTERNAL_ERROR` responses.

These results establish the observed serving behaviour under the tested deployment rather than claiming that the 200 ms target was achieved.

### Batch inference

The k6 script also supports batch inference.

For a 100-row batch:

```bash
k6 run \
  -e TARGET=https://<endpoint>/predict/batch \
  -e VUS=1 \
  -e BATCH=true \
  -e BATCH_SIZE=100 \
  loadtest/k6.js
```

The recorded batch experiment produced:

* Batch size: 100
* Batch requests: 357
* Predictions processed: 35,700
* Batch request throughput: 5.9496 batches/s
* Prediction throughput: approximately 594.96 predictions/s
* Batch p50: 140.8 ms
* Batch p95: 265.8 ms
* Batch p99: 461.0 ms
* Batch errors: 0%

Batch inference therefore substantially increased prediction throughput compared with individual prediction requests, although individual batch-request latency exceeded the 200 ms p95 target.

### Payload-size experiment

The load-test script supports payload-size experiments while keeping the prediction features unchanged.

The recorded results were:

| Payload | Requests | p50 (ms) | p95 (ms) | p99 (ms) | Error rate | Throughput (req/s) |
| ------: | -------: | -------: | -------: | -------: | ---------: | -----------------: |
|    1 KB |      444 |    124.6 |    164.2 |    220.2 |         0% |               7.40 |
|   10 KB |      426 |    129.8 |    212.2 |    266.9 |         0% |               7.09 |
|  100 KB |       53 |    941.4 |  2,029.3 |  2,349.3 |         0% |               0.88 |
|  500 KB |       87 |    521.9 |  1,384.1 |  1,578.7 |         0% |               1.43 |

The 1 KB payload met the pre-declared p95 target.

At 10 KB, p95 slightly exceeded the target.

The 100 KB and 500 KB payloads caused substantial latency and throughput degradation despite returning successful HTTP responses.

This demonstrates that unnecessarily large request payloads can become a serving bottleneck even when the inference application itself continues returning successful predictions.

### Canary and rollback

The intended Lab 3 canary workflow is to deploy a second revision and route a controlled percentage of traffic to it, for example:

```text
blue: 90%
green: 10%
```

The repository contains the canary/rollback implementation for this workflow.

However, the Azure Container Apps environment available for this deployment is an **Express environment**. Express environments do not support switching from single active revision mode to multiple active revision mode.

The attempted revision-mode change failed with the exact Azure error:

```text
(ExpressEnvironmentFeatureNotSupported)
'Not Single Active Revisions Mode' is not supported on express environments.
```

Therefore, a **concurrent 90/10 traffic split between two active revisions could not be performed in this environment**.

This is an Azure Container Apps platform restriction rather than an application or FastAPI implementation error. It cannot be solved by changing the prediction service code.

Consequently, the repository should not claim that a true concurrent 90/10 blue/green split was successfully achieved in this Express environment.

The canary/rollback helper remains in the repository because it implements the intended deployment workflow and can be used in an Azure Container Apps environment that supports multiple active revisions.

### Cost

Serving cost is estimated using the measured serving throughput, the instance hourly rate, and an assumed utilisation level.

The project uses the following cost model:

```text
cost = hourly_rate × (1000 / (throughput × utilisation)) / 3600
```

The current `Standard_DS2_v2` pricing estimate is approximately:

```text
11.1955 THB/hour
```

The previous measured DS2_v2 throughput used for the cost calculation was:

```text
6.671472 predictions/s
```

The estimated cost per 1,000 predictions is:

| Utilisation | THB / 1,000 predictions |
| ----------: | ----------------------: |
|          5% |                  9.3229 |
|         25% |                  1.8646 |
|         80% |                  0.5827 |

The 80% utilisation figure is used as the primary estimate, while the other utilisation levels are shown because utilisation is an important assumption for a continuously running serving instance.

The cost analysis also considers the advantage of batching: batch inference can process substantially more predictions per second, which can reduce the compute cost per prediction when the application's latency requirements allow batching.

The detailed cost analysis is documented in:

```text
reports/lab3-report.md
```

An additional cost-report artifact is retained at:

```text
reports/lab5-cost.md
```

This file originates from the supplied scaffold and contains the project's cost-report calculations. It is retained as supporting cost information; the authoritative Lab 3 cost analysis is `reports/lab3-report.md`.

### Teardown

Lab 3 resources should not be left running after testing.

Use:

```bash
make teardown
```

The teardown implementation uses the Lab 3 resource tags so that resources created for the exercise can be removed without manually tracking every generated resource name.

### Validation

The final automated test suite passes:

```text
34 passed, 1 warning
```

The warning is a dependency deprecation warning and does not cause the test suite to fail.

The serving container was also manually tested through:

```text
GET  /health
GET  /ready
POST /predict
```

All returned successful responses during the local container verification.

### Lab 3 evidence

The main Lab 3 evidence files are:

```text
reports/lab3-report.md
reports/lab3-load.md
loadtest/k6.js
service/Dockerfile.serve
cloudlayer/azure.py
scripts/canary_roll.py
Makefile
```

The repository therefore provides evidence for:

* FastAPI model serving
* model loading during startup
* health and readiness checks
* single prediction
* batch prediction
* containerisation
* `linux/amd64` serving-image construction
* pre-declared p95 latency target
* concurrency testing
* percentile latency measurements
* error-rate measurements
* batch-throughput measurements
* payload-size experiments
* serving-cost analysis
* deployment and teardown logic
* attempted canary/multiple-revision deployment

The main limitation is the Azure Container Apps Express environment's inability to support multiple active revisions. This prevented the intended concurrent 90/10 canary traffic split, and the exact Azure platform error is preserved above.

### Conclusion

Lab 3 successfully demonstrates the provider-independent serving workflow, containerised model inference, health and readiness checks, single and batch inference, percentile-based load testing, payload-size experiments, deployment, cost analysis, and teardown.

The experiments also establish important serving limitations. The declared p95 target of 200 ms was not met by the later authenticated baseline measurements, and reliability degraded beyond the tested 2-VU range. Batch inference substantially increased prediction throughput, while unnecessarily large payloads substantially increased latency.

The intended concurrent canary traffic split could not be completed because the available Azure Container Apps Express environment does not support multiple active revisions. The exact platform error was:

```text
(ExpressEnvironmentFeatureNotSupported)
'Not Single Active Revisions Mode' is not supported on express environments.
```

This limitation is documented explicitly rather than presenting an unsupported 90/10 canary as successfully completed.

