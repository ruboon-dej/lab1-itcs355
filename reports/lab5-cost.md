# Lab 5 — Cost report

Provider `azure` · reference instance `Standard_DS2_v2` · 11.20 THB/hour

> Note: This file is retained as a supporting cost-report artifact from the supplied project material. The billing values below are not used as evidence for the Lab 3 Container Apps serving-cost calculation.

## 1. Reference estimate

25.00 THB

This is the estimate recorded by the supplied cost-report scaffold.

## 2. Billing value in the supplied scaffold

22.00 THB

This value is retained from the supplied project material but is **not** treated as verified Lab 3 Container Apps billing.

## 3. Difference recorded by the scaffold

-3.00 THB (-12.0%)

Because the supplied billing values are not being used as evidence for the final Lab 3 Container Apps deployment, this difference is not interpreted as an actual Lab 3 billing gap.

## 4. Component breakdown

| Component | THB | Notes |
|---|---:|---|
| Training | — | Not separately verified for the final Lab 3 cost analysis |
| Storage | — | Not separately verified |
| Serving | — | Not separately verified as Container Apps billing |
| Pipeline | — | Not separately verified |
| Monitoring | — | Not separately verified |

No component-level Azure billing breakdown was available that could be reliably attributed to the final Lab 3 Container Apps deployment.

## 5. Lab 3 serving-cost sensitivity analysis

The Lab 3 report uses the following reference pricing model:

```text
cost = hourly_rate × (1000 / (throughput × utilisation)) / 3600
```

Reference hourly rate:

```text
11.1955 THB/hour
```

The later authenticated 1-VU load test measured approximately:

```text
6.08 requests/s
```

Using that measured throughput with the reference hourly rate gives the following illustrative sensitivity analysis:

| Utilisation | THB / 1,000 requests |
| ----------: | -------------------: |
|          5% |                10.23 |
|         25% |                 2.05 |
|         80% |                 0.64 |

These values are estimates only. They should not be interpreted as actual Azure Container Apps charges because the hourly rate is based on the project's `Standard_DS2_v2` reference pricing rather than a verified Container Apps billing meter.

The Container Apps deployment is intended to support scale-to-zero. Consequently, actual serving cost depends on how long the application is actively running and the actual Container Apps billing model, rather than simply assuming a continuously running DS2_v2 instance.

## 6. Cost interpretation

The most important limitation of this calculation is that the project does not have a verified Container Apps billing breakdown for the final Lab 3 deployment.

Therefore:

* the `6.08 req/s` value is a real measured load-test result;
* `11.1955 THB/hour` is a reference pricing assumption;
* the three THB-per-1,000 values are sensitivity estimates;
* the `25 THB` and `22 THB` values above are retained from the supplied scaffold but are not claimed as verified Lab 3 Container Apps billing.

This keeps the cost analysis reproducible without presenting unverified billing data as actual deployment cost.

```

**This is the safer version for submission.** It keeps the existing cost artifact, but makes it crystal clear that the `25/22 THB` numbers aren't being passed off as actual Lab 3 Container Apps billing.
```
