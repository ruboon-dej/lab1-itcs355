# Lab 3 — Task 4 canary evidence (standard Container Apps environment)

Resource group `itcs355-6688022`, region Japan East. Times are local (+07) unless marked UTC.
Everything below is copied from terminal output; nothing is reconstructed.

## 1. Why the first attempt failed

All four environments I had created earlier were **Express** environments. Each rejected a
multi-revision app. Probe used on each (a throwaway app, deleted straight after):

```bash
az containerapp create -n probe -g itcs355-6688022 --environment <env> \
  --image mcr.microsoft.com/azuredocs/containerapps-helloworld:latest \
  --revisions-mode multiple --min-replicas 0 --max-replicas 1
```

Identical error for `itcs355-6688022-cae`, `itcs355-itcs355-6688022-cae`,
`itcs355-itcs355-6688022-cae2` and `itcs355-itcs355-6688022-cae-wp`:

```
ERROR: (ExpressEnvironmentFeatureNotSupported) 'Not Single Active Revisions Mode ' is not
supported for container app 'probe' on express environments. Please remove
'properties.configuration.activeRevisionsMode' from the request.
```

## 2. How the Express environments were created

Shell history shows every one was created with plain
`az containerapp env create --name ... --resource-group ... --location japaneast`
(the 24 Sep one also with `--enable-workload-profiles`). No Express flag was passed, and
`az containerapp up` was never run. The installed `containerapp` extension did not list
`--environment-mode` until it was reinstalled (version 1.3.0b5).

## 3. Fix: a standard (Consumption-only) environment

```bash
az containerapp env create -n itcs355-std -g itcs355-6688022 --location japaneast \
  --environment-mode ConsumptionOnly --logs-destination none
```

Result: `"environmentMode": "ConsumptionOnly"`, `"workloadProfiles": null`,
`createdAt 2026-10-23T19:58:45Z`. The same probe then **succeeded** with
`"activeRevisionsMode": "Multiple"`, and was deleted.

## 4. Deployment and canary

`AZURE_CONTAINERAPPS_ENVIRONMENT=itcs355-std`, `ENDPOINT_NAME=itcs355-6688022-staging`.

- `make deploy` created the app in `itcs355-std` (production revision
  `itcs355-6688022-staging--0000001`, model `itcs355-6688022:2`).
- `make canary` set Multiple mode, created revision `--0000002`, and printed:

```
Traffic set: itcs355-6688022-staging--0000001=90, itcs355-6688022-staging--0000002=10
```

Sat Oct 24 03:30:10 +07 2026, `az containerapp revision list`:

| Name | Traffic | Running | Health |
|---|---|---|---|
| itcs355-6688022-staging--0000001 | 90 | ScaledToZero | Healthy |
| itcs355-6688022-staging--0000002 | 10 | ScaledToZero | Healthy |

## 5. Traffic really shifted (50 requests, `make smoke`)

03:33:16 to 03:48:22 +07:

```
 45 {'probability': 0.05148928384502734, 'model_version': '2'}
  5 {'probability': 0.05148928384502734, 'model_version': '3'}
```

45/5 is exactly 90/10.

## 6. Rollback

03:53:24 to 03:54:57 +07, `make rollback`:

```
Traffic set: itcs355-6688022-staging--0000001=100
Rollback done.
```

`az containerapp ingress traffic show` afterwards: `--0000001  100`.

Re-test after rollback, 03:56:22 to 03:58:29 +07 (15 requests):

```
 15 {'probability': 0.05148928384502734, 'model_version': '2'}
```

## 7. Caveat (stated plainly)

Both revisions run the **same image** (digest `sha256:18e6ca365e67...`). `deploy_canary`
re-pushes the local image and only sets `MODEL_VERSION=3`, which the service reports.
The probability is identical for both labels (0.0514892838...), so this proves the traffic
split and rollback mechanism on a standard environment. It is not a comparison of two
different models. A 90/10 split of two real models would differ only in the weights baked
into the second image.

## 8. Cleanup

Sat Oct 24 2026, Sat Oct 24 10:36:32 +07 2026:

- `az containerapp delete -n itcs355-6688022-staging` → "Containerapp successfully deleted"
- Environments deleted: `itcs355-std`, `itcs355-6688022-cae`, `itcs355-itcs355-6688022-cae`,
  `itcs355-itcs355-6688022-cae2`, `itcs355-itcs355-6688022-cae-wp` (each "successfully deleted")
- `az containerapp env list -g itcs355-6688022 -o table` → empty
- Three auto-created Log Analytics workspaces (`workspace-itcs3556688022cxif`, `...pM50`, `...ffY5`)
  deleted. `az monitor log-analytics workspace list` shows only the original
  `itcs3556logalyti4407d67d`.
- Still present: container registry `itcs3556688022`, kept until the lab is accepted.
