## Lab 4 — CI/CD, observability and drift

### Pipeline
`ci.yml` (pull request and push to main): lint → portability audit → data contract tests → model behaviour tests → service and metrics tests → build both images → integration test (container started, `/predict` called, response checked). `cd.yml` runs only on main, only when CI succeeded, only through the `staging` environment: it checks out the tested commit, rebuilds the serving image tagged with the commit SHA (never `latest`), pushes it, deploys to Azure Container Apps and smoke-tests three known payloads, asserting that the deployed `model_version` equals the commit SHA.

### Tests and the incident each would catch
| Test | Production incident it catches |
|---|---|
| `test_schema_columns_present_and_typed` | an upstream team renames, drops or retypes a column |
| `test_no_nulls_in_required_columns` | a sensor outage or a broken join starts filling features with nulls |
| `test_features_within_plausible_ranges` | a unit change (°C → °F) or a stuck sensor |
| `test_target_is_binary_and_not_degenerate` | the labelling job breaks and every row gets the same label |
| `test_identifier_is_unique` | a duplicated ingestion batch |
| `test_no_machine_leaks_across_splits` | leakage: the same machine in train and test inflates the metric |

Model behaviour: valid probabilities, a known healthy machine scores low, risk does not fall as wear rises, the model is not constant, and a single prediction stays under 50 ms. That budget is a quarter of the 200 ms p95 target, leaving the rest for network, JSON and queueing; measured at about 5 ms, so there is ~10x headroom for a noisy CI runner.

### Blocked bad commit (Task 3)
Evidence: PR `<link>` · failing run `<link>` · failing test `<name>` · error `<paste>`. Closed without merging.

### Credentials: OIDC without an app registration
`az ad app create` fails in the university tenant ("Insufficient privileges"), so the usual GitHub-to-Azure OIDC setup was unavailable. A user-assigned managed identity (`itcs355-gh-deploy`) carries a federated credential scoped to `repo:ruboon-dej/lab1-itcs355:environment:staging`, with AcrPush on the registry and Contributor on the resource group only. It gives the same keyless login and needs only Azure RBAC on my own resource group. No key is stored for Azure login (the three IDs in repository secrets are identifiers, not credentials).

### Dashboard
Prometheus + Grafana, run locally (`docker compose -f monitoring/docker-compose.yml up -d`), dashboard as code: `monitoring/dashboard.json` is the source and `scripts/build_grafana_dashboard.py` generates the Grafana file. Panels: request rate; error rate split 4xx/5xx; latency p50/p95/p99; per-feature PSI; model version in production; rolling mean of every input feature over the last 500 requests (the feature-distribution statistic, computed inside the service). The service runs with one worker for the demo because `prometheus_client` counters are per process. **Local, not live:** the Azure deployment scales to zero and is torn down after the lab, so a dashboard pointed at it would have nothing to show.

### SLO (`monitoring/slo.yaml`)
Availability 0.99 over 30 days (the app has a single replica scaling to zero, so a higher promise would be one the architecture cannot keep); latency p95 200 ms (honest status: Lab 3 measured 233 ms at 1 VU, so this is not currently met); freshness 30 days. Each has a stated response when the budget is spent. Rollback is "redeploy the previous SHA-tagged image", because the traffic-split rollback from Lab 3 could not run in this environment (`ExpressEnvironmentFeatureNotSupported`).

### Drift detection
PSI and KS per feature (`monitoring/drift.py`), run by `.github/workflows/drift.yml` on a schedule. **Threshold 0.09, with a reason:** PSI is biased upward at small windows, so I measured the noise instead of copying a tutorial. `scripts/calibrate_drift_threshold.py` generated 200 fresh datasets from the same process, took 500-row windows, and computed PSI against the reference for all six features. The detector alerts when any feature crosses the line, so the relevant statistic is the maximum across features per trial: median 0.046, 99th percentile 0.0895, rounded up to 0.09 (`monitoring/drift_threshold.json`). That is about 1 false alarm per 100 checks. The conventional 0.10 / 0.25 values come from credit scoring with large stable volumes. At this window 0.25 would be far too loose: a +3 shift in `temp_c` scores 0.12 and a 1.5x spread change scores 0.27, so a 0.25 threshold would miss the shift entirely.

Observed on the simulated window: no injection → no alert; shift +1 → PSI 0.055, no alert; shift +3 → 0.122, alert; shift +6 → 0.344, alert; scale ×1.5 → 0.273, alert; scale ×2 → 0.525, alert; mix → `hours_since_service` and `load_pct` alert while `temp_c` stays at 0.046 (the hard one: the fleet changed, not the feature). KS reacts more to location shifts and PSI to spread changes.

Schedule: GitHub Actions cron every 15 minutes while `DRIFT_ENABLED=true`. Score: sent to Application Insights as `drift.psi.<feature>` through `adapter.emit_metric()`. Alert: webhook to `<Slack/Discord/Telegram>` plus GitHub's failed-run email (the job exits 2 on a breach). Check delivery in Application Insights → Logs: `customMetrics | where name startswith "drift.psi" | order by timestamp desc | take 20`.

### Injected drift exercise (Task 6)
t0 (injection variable set): `<time>` · alert timestamp: `<time>` · **detection time: `<alert − t0>`** · dashboard screenshot: `<file>` · alert screenshot: `<file>`.

```
What fired:
True cause:
Retrain, roll back, or no action — and why:
What this would have cost if unnoticed for a week:
How to prevent or detect it faster:
```
Before choosing "retrain": did the schema or null rate change? If so, an upstream pipeline broke and retraining on that data would make things permanently worse.

### Substitutions and limitations (and why)
- **Federated login via managed identity**, not an Entra app registration: blocked by the tenant (above).
- **Scheduler is GitHub Actions cron**, not an Azure scheduler: an Azure ML schedule needs compute and Azure for Students does not allow VM compute quota requests. Trade-offs: GitHub may delay scheduled runs; the job runs outside Azure and is ephemeral, which is why the score is sent to Azure Monitor.
- **Dashboard is local**, not fed by the live endpoint (reason above).
- **Alert goes to a webhook, not Line Notify**, which LINE shut down on 31 March 2025.
- **"Production inputs" are simulated.** The service receives no real traffic, so the current window is fresh data from the same process (a different seed per run) with a controlled shift. Detection time measures this pipeline, not a real incident.
- **ACR admin credential:** the Lab 3 adapter enables the registry admin user and stores its password as a Container App secret. CI login is keyless, but the running app still pulls with a static credential.
- **Requirements:** `requirements.in` does not compile as written (`mlflow==3.16.0` needs `mlflow-skinny==3.16.0`, but `azureml-mlflow` needs `<=3.15.0`, which in turn needs `pandas<3`). Left untouched; CD and drift use a separate hash-locked `requirements-ops.txt` with no mlflow.
- **Metric delivery:** the Azure Monitor exporter retries in the background and does not report failure to the caller, so "metrics handed to the cloud exporter" in the drift log is not proof of delivery; confirm with the query above.

### Teardown
Disable the drift schedule (set `DRIFT_ENABLED=false`), delete the staging Container App, run `make teardown` and `make cost-report`. `make teardown` does not remove the managed identity or its role assignments; remove those separately if not needed for later labs.
