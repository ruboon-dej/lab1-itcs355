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
Training ran on Azure ML managed compute (Standard_DS3_v2, dedicated tier — the
workspace had no low-priority/spot quota available). Compute scales to 0 when idle.

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

The cost for training was 0.19 THB/trial and total cost for the study was 2.91 THB, clearly below the budget of 150 THB. Given the cost per trial, the retraining on one configuration alone would cost 0.19 THB.

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
| DVC data version | `1c886b512c8a5c9bf723da1cd119fc80.dir` |
| MLflow run ID | `a81deea37f9b4659addf64908d518e7b` |
| Training job | `mango_boot_pbpr17lrhb` |
| Image digest | `sha256:585f50972aa5afd104c6b337fd23716a82276cb9b6a5401d7f8a0dbaf64a0d7a` |
| Seed | `20260102` |
| Val / Test ROC-AUC | `0.8733` / `0.8463` |

### Registry
Registered as `itcs355-6688022:1` with the lineage above as tags, plus
`stage=staging`. The installed Azure ML SDK (`azure-ai-ml 1.35.0`) had no
public native stage-promotion API, so staging is represented with a `stage` tag.

### Promotion policy
Promotion should be managed by an appointed ML Engineer/Release Owner, and not the trainer. Evidence required: Git Commit, Data Version, MLflow Run ID, Training Job ID, Image Digest, Seed, Validation/Test Metrics, Baseline Comparison, Registry Reload Success, and Cost Profile Approval.

### Reload check
`reload_check.py` downloaded `itcs355-6688022:1` directly from the registry,
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