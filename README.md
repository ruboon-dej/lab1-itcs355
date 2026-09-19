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
from the fixed seedvia `scripts/make_dataset.py`, with no dependency on DVC or cloud access.

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

Seed 20260102 was chosen since validation performance is used for choosing the model; the test set is kept held-out. Even though seed 20260101 had a slightly better score on the test set, using the performance on the test set for choosing the model leaks information about the held-out data.

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
Promotion of the ML model should be done by the ML engineer or release owner, and not all developers who are capable of training ML models. It will be the responsibility of the reviewer to demand proof of a reproducible lineage for the registered model before it is promoted, and these include: Git commit, DVC data version, MLflow run ID, training job ID, container image digest, seed, and validation/test metrics. The selected model should have documented evaluation against the candidate configurations and a successful reload check from the model registry.

### Reload check
`reload_check.py` downloaded `itcs355-6688022:2` directly from the registry,
deserialized it, and scored 5 held-out rows — **PASS**.

**Known limitation:** `reload_check.py` splits the data with `seed=20260101`,
while the registered model was trained using data generated with
`seed=20260102`. This proves the registry-to-inference path works but is not an
exact reproduction of the original evaluation split.

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
`Ctrl-C` while the checkpoint file remained intact.

The interruption evidence is preserved in
`reports/interrupt-resume-log.txt`. It records the checkpoint surviving the
local `Ctrl-C` interruption and the subsequent resume behavior. The resume test then confirmed that
the completed trial was skipped and a subsequent trial could be recorded.

An actual Azure ML LowPriority interruption could not be demonstrated because
the required LowPriority compute could not be provisioned under the available
Azure for Students quota.