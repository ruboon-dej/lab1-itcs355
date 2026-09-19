import contextlib
import io
import json
import os
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

import scripts.tune_remote as tune_remote


class FakeMLflow:
    def set_tracking_uri(self, uri):
        pass

    def start_run(self, run_id):
        return contextlib.nullcontext()

    def log_metrics(self, metrics):
        pass

    def set_tags(self, tags):
        pass


class FakeAdapter:
    def __init__(self, interrupt_on_second=False):
        self.interrupt_on_second = interrupt_on_second
        self.wait_count = 0
        self.submit_count = 0

    def submit_training(self, image_uri, train_args):
        self.submit_count += 1
        return f"fake-job-{self.submit_count}"

    def wait_training(self, job_id):
        self.wait_count += 1

        if self.interrupt_on_second and self.wait_count == 2:
            raise KeyboardInterrupt

        return {
            "mlflow_run_id": f"fake-run-{self.wait_count}",
            "data_fingerprint": "fake-fingerprint",
            "data_version": "fake-data-version",
            "git_commit": "fake-git-commit",
            "image_digest": "fake-image-digest",
            "training_duration_s": 1.0,
            "val_roc_auc": 0.84,
            "val_pr_auc": 0.39,
            "test_roc_auc": 0.85,
            "test_pr_auc": 0.49,
            "studio_url": f"https://example.com/{job_id}",
        }


def fake_config():
    return SimpleNamespace(
        provider="azure",
        mlflow_tracking_uri="file:./mlruns",
    )


def run_controller(checkpoint, adapter):
    old_argv = sys.argv[:]
    sys.argv = [
        "tune_remote.py",
        "--trials",
        "3",
        "--budget-thb",
        "150",
        "--checkpoint",
        str(checkpoint),
    ]

    old_get_adapter = tune_remote.get_adapter
    old_config_load = tune_remote.config.load
    old_hourly_rate = tune_remote.costs.hourly_rate
    old_set_all = tune_remote.seeds.set_all
    old_mlflow = tune_remote.mlflow

    tune_remote.get_adapter = lambda cfg: adapter
    tune_remote.config.load = lambda strict=False: fake_config()
    tune_remote.costs.hourly_rate = lambda provider, instance, spot: 1.0
    tune_remote.seeds.set_all = lambda seed: seed
    tune_remote.mlflow = FakeMLflow()

    try:
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            try:
                tune_remote.main()
            except KeyboardInterrupt:
                print("INTERRUPTED: controller stopped.")
        return output.getvalue()
    finally:
        tune_remote.get_adapter = old_get_adapter
        tune_remote.config.load = old_config_load
        tune_remote.costs.hourly_rate = old_hourly_rate
        tune_remote.seeds.set_all = old_set_all
        tune_remote.mlflow = old_mlflow
        sys.argv = old_argv


def test_tune_remote_checkpoint_resume():
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        checkpoint = tmp_path / "tune_remote_checkpoint.json"

        old_cwd = Path.cwd()
        os.chdir(tmp_path)

        try:
            Path(".image_uri").write_text("fake-image@sha256:fake\n")

            first_adapter = FakeAdapter(interrupt_on_second=True)
            first_output = run_controller(checkpoint, first_adapter)

            state_after_interrupt = json.loads(checkpoint.read_text())

            assert len(state_after_interrupt["completed"]) == 1
            assert len(state_after_interrupt["trials"]) == 1
            assert state_after_interrupt["trials"][0]["status"] == "completed"

            second_adapter = FakeAdapter()
            second_output = run_controller(checkpoint, second_adapter)

            final_state = json.loads(checkpoint.read_text())

            assert len(final_state["completed"]) == 3
            assert len(final_state["trials"]) == 3
            assert all(
                trial["status"] == "completed"
                for trial in final_state["trials"]
            )

            assert "trial 0: already done, skipping (resumed from checkpoint)" in second_output

            print("=== FIRST RUN ===")
            print(first_output.rstrip())

            print("\n=== CHECKPOINT AFTER INTERRUPTION ===")
            print(json.dumps(state_after_interrupt, indent=2))

            print("\n=== SECOND RUN / RESUME ===")
            print(second_output.rstrip())

            print("\n=== FINAL CHECKPOINT ===")
            print(json.dumps(final_state, indent=2))

            print("\nPASS: tune_remote.py checkpoint/resume behavior works")

        finally:
            os.chdir(old_cwd)

if __name__ == "__main__":
    test_tune_remote_checkpoint_resume()