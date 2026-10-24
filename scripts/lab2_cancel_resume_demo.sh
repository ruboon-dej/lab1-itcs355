#!/usr/bin/env bash
# Lab 2 evidence: cancel one Azure ML trial mid-run, then resume the study from its checkpoint.
#
#   bash scripts/lab2_cancel_resume_demo.sh
#
# What it does (nothing needs to be timed by hand):
#   0. pre-flight: Azure login, compute cluster and data asset exist, otherwise stop BEFORE spending money
#   1. RUN 1: starts a 3-trial study on Dedicated compute
#   2. as soon as trial 1's job is in flight, waits ~20 s and cancels it (az ml job cancel)
#   3. lets the study finish (trial 2 completes), then checks trial 0 completed
#   4. RUN 2: starts the same study again -> trials 0 and 2 must be skipped, trial 1 resubmitted
#   5. prints a summary and writes everything, with timestamps, to reports/lab2-cancel-resume-log.txt
#
# Overridable for testing: AZ, PYTHON, CONTROLLER.
set -u

AZ=${AZ:-az}
PYTHON=${PYTHON:-python}
CONTROLLER=${CONTROLLER:-scripts/tune_remote.py}
RG=${RG:-itcs355-6688022}
WS=${WS:-itcs355-6688022-ws}
TRIALS=3
CANCEL_DELAY=${CANCEL_DELAY:-20}

export AZURE_ML_COMPUTE=${AZURE_ML_COMPUTE:-lab2-dedicated}
export LAB2_TRAINING_DATA=${LAB2_TRAINING_DATA:-azureml:lab2-sensors:1}
export LAB2_JOB_LOCAL_MLFLOW=1

CK=reports/tune_demo_checkpoint.json
LOG=reports/lab2-cancel-resume-log.txt

mkdir -p reports
stamp() { echo "[$(date '+%Y-%m-%d %H:%M:%S %z')] $*" | tee -a "$LOG"; }
die()   { stamp "STOP: $*"; exit 1; }

rm -f "$CK" "$LOG"
stamp "Lab 2 cancel-and-resume demo (compute=$AZURE_ML_COMPUTE, data=$LAB2_TRAINING_DATA)"

# ---------------------------------------------------------------- pre-flight
stamp "pre-flight checks"
$AZ account show --query name -o tsv >/dev/null 2>&1 \
  || die "not logged in to Azure. Run: az login"
$AZ ml compute show -n "$AZURE_ML_COMPUTE" -g "$RG" -w "$WS" --query name -o tsv >/dev/null 2>&1 \
  || die "compute cluster '$AZURE_ML_COMPUTE' not found in workspace $WS"
NAME_VER=${LAB2_TRAINING_DATA#azureml:}
DATA_NAME=${NAME_VER%%:*}
DATA_VER=${NAME_VER##*:}
$AZ ml data show --name "$DATA_NAME" --version "$DATA_VER" -g "$RG" -w "$WS" --query name -o tsv >/dev/null 2>&1 \
  || die "data asset $LAB2_TRAINING_DATA not found"
[ -f .image_uri ] || die ".image_uri not found (run make image-push first)"
stamp "pre-flight OK"

summary() {
  $PYTHON - "$CK" <<'PY'
import json, sys
try:
    d = json.load(open(sys.argv[1]))
except Exception as e:
    print("  (no checkpoint yet:", e, ")"); raise SystemExit
for t in d["trials"]:
    print(f"  trial {t['trial']}: {t['status']:<10} job={t['job_id']} duration={t['duration_s']}s cost={t['cost_thb']} THB")
print(f"  completed trials in checkpoint: {len(d['completed'])}   spent: {d['spent_thb']:.4f} THB")
PY
}

n_completed() {
  $PYTHON -c "import json,sys;print(len(json.load(open('$CK'))['completed']))" 2>/dev/null || echo 0
}

# ---------------------------------------------------------------- RUN 1
stamp "RUN 1: starting study ($TRIALS trials). Trial 1 will be cancelled mid-run."
$PYTHON -u "$CONTROLLER" --trials $TRIALS --tier dedicated --checkpoint "$CK" >> "$LOG" 2>&1 &
PID=$!

CANCELLED=""
while kill -0 "$PID" 2>/dev/null; do
  if [ -z "$CANCELLED" ]; then
    # the controller prints "trial 1: job <name> submitted" the moment it submits trial 1
    JOB=$(grep -o 'trial 1: job lab2-trial-[a-z0-9]* submitted' "$LOG" | head -1 | awk '{print $4}')
    if [ -n "$JOB" ]; then
      stamp "trial 1 job $JOB submitted; cancelling in ${CANCEL_DELAY}s so it is genuinely mid-run"
      sleep "$CANCEL_DELAY"
      NOW=$($AZ ml job show -n "$JOB" -g "$RG" -w "$WS" --query status -o tsv 2>/dev/null)
      case "$NOW" in
        Completed|Failed|Canceled)
          stamp "job $JOB already finished ($NOW) before it could be cancelled"
          CANCELLED="none" ;;
        *)
          stamp "CANCEL: az ml job cancel -n $JOB (status was $NOW)"
          $AZ ml job cancel -n "$JOB" -g "$RG" -w "$WS" >> "$LOG" 2>&1
          CANCELLED="$JOB" ;;
      esac
    fi
  fi
  sleep 3
done
wait "$PID"
stamp "RUN 1 finished (controller exit code $?)"
[ "$CANCELLED" = "none" ] && die "trial 1 finished before it could be cancelled, so the demo is not valid. Re-run the script."
[ -n "$CANCELLED" ] || die "no second trial job was ever seen, so nothing was cancelled"
stamp "cancelled job: $CANCELLED; final status: $($AZ ml job show -n "$CANCELLED" -g "$RG" -w "$WS" --query status -o tsv 2>/dev/null)"
stamp "checkpoint after RUN 1:"
summary | tee -a "$LOG"

[ "$(n_completed)" -ge 1 ] || die "no trial completed in RUN 1, so there is nothing to resume from. Check the job errors with az ml job stream"

# ---------------------------------------------------------------- RUN 2
stamp "RUN 2: same command again. Expect completed trials to be skipped and the cancelled trial resubmitted."
$PYTHON -u "$CONTROLLER" --trials $TRIALS --tier dedicated --checkpoint "$CK" 2>&1 | tee -a "$LOG"
stamp "checkpoint after RUN 2:"
summary | tee -a "$LOG"

stamp "DONE. Evidence: $LOG and $CK"
grep -c "already done, skipping (resumed from checkpoint)" "$LOG" | sed 's/^/skipped-on-resume count: /' | tee -a "$LOG"
