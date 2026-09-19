"""Azure adapter. Implement upload/download/push_image for Lab 1.

SDK:  pip install azure-storage-blob azure-identity azure-containerregistry
Docs: BlobServiceClient for storage; ACR push goes through `docker push` after
      `az acr login --name <registry>`.

Hints for Lab 1:
  * BLOB_URI is either abfss://container@account.dfs.core.windows.net/prefix or
    https://account.blob.core.windows.net/container/prefix. Pick one form and parse
    it here, never in src/.
  * Use DefaultAzureCredential rather than a connection string. It picks up your CLI
    login locally and your managed identity in CI, which is what Lab 4 needs.
  * push_image must return the digest reference: registry.azurecr.io/repo@sha256:...
  * Azure tags live on the resource, not the blob. Tag the storage account, the
    registry, and later the workspace with cfg.tags(1).
"""
from __future__ import annotations

import subprocess
from pathlib import Path
import time
from typing import Any
from urllib.parse import urlparse

from azure.ai.ml import Input, MLClient, Output, command
from azure.ai.ml.entities import Environment, Model
from azure.ai.ml.constants import AssetTypes
from azure.identity import DefaultAzureCredential

from cloudlayer.base import CloudAdapter
import os
import json
import re
import tempfile
import uuid


def _parse_blob_uri(blob_uri: str) -> tuple[str, str, str]:
    """Parse https://<account>.blob.core.windows.net/<container>/<prefix> into
    (account, container, prefix)."""
    parsed = urlparse(blob_uri)
    account = parsed.netloc.split(".")[0]
    parts = parsed.path.strip("/").split("/", 1)
    container = parts[0]
    prefix = parts[1] if len(parts) > 1 else ""
    return account, container, prefix


class AzureAdapter(CloudAdapter):
    def register_model(
        self,
        model_uri: str,
        name: str,
        tags: dict[str, str] | None = None,
    ) -> str:
        """Register an MLflow model while preserving run/job lineage."""
        ml_client = self._ml_client()

        if model_uri.startswith("runs:/"):
            model_type = AssetTypes.MLFLOW_MODEL
        else:
            model_path = Path(model_uri)
            if not model_path.exists():
                raise FileNotFoundError(
                    f"Model artifact not found: {model_path}"
                )
            model_type = AssetTypes.CUSTOM_MODEL

        model = Model(
            path=model_uri,
            name=name,
            type=model_type,
            description="ITCS355 Lab 2 selected RandomForest model",
            tags=tags or {},
        )

        registered = ml_client.models.create_or_update(model)

        print(
            f"Registered model: {registered.name}, "
            f"version: {registered.version}"
        )

        return str(registered.version)

    def _blob_service_client(self):
        from azure.identity import DefaultAzureCredential
        from azure.storage.blob import BlobServiceClient

        account, _, _ = _parse_blob_uri(self.cfg.blob_uri)
        account_url = f"https://{account}.blob.core.windows.net"
        return BlobServiceClient(account_url=account_url, credential=DefaultAzureCredential())

    def upload(self, local_path: str, key: str) -> str:
        account, container, prefix = _parse_blob_uri(self.cfg.blob_uri)
        blob_name = f"{prefix}/{key}".strip("/") if prefix else key

        client = self._blob_service_client()
        blob_client = client.get_blob_client(container=container, blob=blob_name)
        with open(local_path, "rb") as f:
            blob_client.upload_blob(f, overwrite=True)

        return f"https://{account}.blob.core.windows.net/{container}/{blob_name}"

    def download(self, uri: str, local_path: str) -> None:
        parsed = urlparse(uri)
        container, blob_name = parsed.path.strip("/").split("/", 1)

        client = self._blob_service_client()
        blob_client = client.get_blob_client(container=container, blob=blob_name)

        Path(local_path).parent.mkdir(parents=True, exist_ok=True)
        with open(local_path, "wb") as f:
            f.write(blob_client.download_blob().readall())

    def push_image(self, local_tag: str) -> str:
        import re

        registry_host, repo = self.cfg.container_registry.split("/", 1)
        remote_tag = f"{registry_host}/{repo}:{local_tag.split(':')[-1]}"

        subprocess.run(["docker", "tag", local_tag, remote_tag], check=True)
        push_result = subprocess.run(
            ["docker", "push", remote_tag],
            check=True, capture_output=True, text=True,
        )

        match = re.search(r"digest:\s*(sha256:[0-9a-f]+)", push_result.stdout)
        if not match:
            raise RuntimeError(f"Could not parse digest from docker push output:\n{push_result.stdout}")

        digest = match.group(1)
        return f"{registry_host}/{repo}@{digest}"

    def _ml_client(self) -> MLClient:
        return MLClient(
            credential=DefaultAzureCredential(),
            subscription_id=os.environ["AZURE_SUBSCRIPTION_ID"],
            resource_group_name=os.environ["AZURE_RESOURCE_GROUP"],
            workspace_name=os.environ["AZURE_ML_WORKSPACE"],
        )

    def _mlflow_tracking_uri(self) -> str:
        return self._ml_client().workspaces.get(os.environ["AZURE_ML_WORKSPACE"]).mlflow_tracking_uri

    def submit_training(
        self,
        image_uri: str,
        args: dict[str, Any],
    ) -> str:
        """Submit one Lab 2 training trial to Azure ML."""

        ml_client = self._ml_client()

        compute_name = os.environ.get(
            "AZURE_ML_COMPUTE",
            "lab2-lowpri",
        )

        compute = ml_client.compute.get(compute_name)

        tier = str(
            getattr(
                compute,
                "tier",
                getattr(
                    getattr(compute, "properties", None),
                    "vm_priority",
                    "",
                ),
            )
        ).lower().replace("-", "_")

        if tier not in {"low_priority", "lowpriority"}:
            raise RuntimeError(
                f"Lab 2 requires discounted compute, but compute "
                f"{compute_name!r} reports tier={tier!r}. "
                "Do not submit the study on Dedicated compute."
            )

        cli_args = " ".join(
            f"--{key} {value}"
            for key, value in args.items()
        )

        env = Environment(image=image_uri)

        data_uri = (
            f"{self.cfg.blob_uri.rstrip('/')}"
            "/training-data/sensors.csv"
        )

        output_uri = (
            f"{self.cfg.blob_uri.rstrip('/')}"
            f"/lab2-outputs/{uuid.uuid4().hex}"
        )

        git_sha = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
            cwd=self.cfg.data_dir.parent,
        ).stdout.strip()

        dvc_text = (
            self.cfg.data_dir.parent / "data" / "raw.dvc"
        ).read_text()

        match = re.search(
            r"md5:\s*([0-9a-f]+(?:\.dir)?)",
            dvc_text,
        )

        if not match:
            raise RuntimeError(
                "Could not read the DVC data hash from data/raw.dvc"
            )

        dvc_version = match.group(1)

        image_digest = (
            image_uri.split("@", 1)[1]
            if "@" in image_uri
            else "unknown"
        )

        tracking_uri = self._mlflow_tracking_uri()

        job = command(
            environment=env,

            inputs={
                "training_data": Input(
                    type=AssetTypes.URI_FILE,
                    path=data_uri,
                    mode="ro_mount",
                ),
            },

            command=(
                "cd /app && "
                "python -m src.train "
                f"--data-path ${{{{inputs.training_data}}}} "
                f"{cli_args} "
                "--experiment itcs355-lab2 "
                "--metrics-out ${{{{outputs.model_output}}}}"
            ),

            outputs={
                "model_output": Output(
                    type=AssetTypes.URI_FOLDER,
                    path=output_uri,
                    mode="rw_mount",
                ),
            },

            compute=compute_name,

            environment_variables={
                "BLOB_URI": self.cfg.blob_uri,
                "CLOUD_PROVIDER": "azure",
                "MLFLOW_TRACKING_URI": tracking_uri,
                "GIT_COMMIT": git_sha,
                "DVC_DATA_VERSION": dvc_version,
                "IMAGE_DIGEST": image_digest,
                "INSTANCE_TYPE": "Standard_DS3_v2",
                "COMPUTE_TIER": "low_priority",
            },

            display_name="itcs355-lab2-trial",
            experiment_name="itcs355-lab2",

            tags={
                **self.cfg.tags(2),
                "compute": compute_name,
                "compute_tier": "low_priority",
            },
        )

        submitted = ml_client.jobs.create_or_update(job)

        return submitted.name
 
    def wait_training(self, job_id: str) -> dict[str, Any]:
        """Wait for a training job and recover its recorded metrics."""

        ml_client = self._ml_client()

        terminal = {
            "Completed",
            "Failed",
            "Canceled",
        }

        status = None

        while status not in terminal:
            job = ml_client.jobs.get(job_id)
            status = job.status

            if status not in terminal:
                time.sleep(15)

        if status != "Completed":
            raise RuntimeError(
                f"training job {job_id} ended with status={status}"
            )

        with tempfile.TemporaryDirectory(
            prefix="lab2_job_"
        ) as tmp:

            ml_client.jobs.download(
                name=job_id,
                output_name="model_output",
                download_path=tmp,
            )

            metrics_files = list(
                Path(tmp).rglob("metrics.json")
            )

            if not metrics_files:
                raise FileNotFoundError(
                    f"Job {job_id} completed but no metrics.json "
                    "was found in model_output."
                )

            metrics = json.loads(
                metrics_files[0].read_text()
            )

        return {
            "job_id": job_id,
            "status": status,
            "studio_url": job.studio_url,
            "mlflow_run_id": metrics["mlflow_run_id"],
            "data_fingerprint": metrics["data_fingerprint"],
            "data_version": metrics.get(
                "data_version",
                "unknown",
            ),
            "git_commit": metrics.get(
                "git_commit",
                "unknown",
            ),
            "image_digest": metrics.get(
                "image_digest",
                "unknown",
            ),
            "seed": metrics["seed"],
            "val_roc_auc": metrics["val_roc_auc"],
            "val_pr_auc": metrics["val_pr_auc"],
            "test_roc_auc": metrics["test_roc_auc"],
            "test_pr_auc": metrics["test_pr_auc"],
            "training_duration_s": metrics.get(
                "training_duration_s"
            ),
            "metrics": metrics,
        }
    
    # submit_training / register_model  -> Lab 2 (Azure ML command job + model registry)
    # deploy / invoke                   -> Lab 3 (managed online endpoint + deployment)
    # emit_metric                       -> Lab 4 (Azure Monitor custom metric)
    # generate                          -> Lab 5 (managed LLM endpoint; read the usage block for tokens)
    # teardown                          -> Lab 5 (resource graph query by tag)
