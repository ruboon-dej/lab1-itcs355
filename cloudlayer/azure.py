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

from azure.ai.ml import MLClient, command, Output
from azure.ai.ml.entities import Environment, Model, JobResourceConfiguration
from azure.ai.ml.constants import AssetTypes
from azure.identity import DefaultAzureCredential

from cloudlayer.base import CloudAdapter
import os


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
    def register_model(self, model_uri: str, name: str) -> str:
        """Register the selected model in Azure ML with full lineage."""
        ml_client = self._ml_client()

        model_path = Path(model_uri)
        if not model_path.exists():
            raise FileNotFoundError(f"Model artifact not found: {model_path}")

        model = Model(
            path=str(model_path),
            name=name,
            type=AssetTypes.CUSTOM_MODEL,
            description="ITCS355 Lab 2 selected RandomForest model",
            tags={
                "git_commit": "6ccc5ee0e89d624811802e869f5e4099d1707776",
                "data_version": "1c886b512c8a5c9bf723da1cd119fc80.dir",
                "mlflow_run_id": "a81deea37f9b4659addf64908d518e7b",
                "training_job_id": "mango_boot_pbpr17lrhb",
                "image_digest": "sha256:585f50972aa5afd104c6b337fd23716a82276cb9b6a5401d7f8a0dbaf64a0d7a",
                "seed": "20260102",
                "metric_val": "0.873298156471891",
                "metric_test": "0.8463274932614555",
            },
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

    def submit_training(self, image_uri: str, args: dict[str, Any]) -> str:
        """Run the Lab 1 container as an Azure ML command job.
 
        `args` is whatever CLI flags your training entrypoint takes, e.g.
        {"n-estimators": 200, "max-depth": 8, "seed": 20260101}. This function only
        translates them into a command line; it does not interpret them.
        """
        ml_client = self._ml_client()
 
        cli_args = " ".join(f"--{k} {v}" for k, v in args.items())
 
        # Environment must be an actual Environment object wrapping your image — there is
        # no "docker:<uri>" shorthand. Azure ML will register a new environment version
        # the first time it sees this image; subsequent submissions reuse it.
        env = Environment(image=image_uri)
 
        job = command(
        environment=env,
        command=f"cd /app && python scripts/make_dataset.py --seed {args.get('seed', 20260101)} && "
        f"python -m src.train {cli_args} "
        f"--metrics-out ${{{{outputs.model_output}}}}/metrics.json",
        outputs={
            "model_output": Output(
                type="uri_folder",
                mode="rw_mount",
            ),
        },
            # TODO(Lab 2): the name of an AmlCompute cluster you created ahead of time,
            # e.g. via `az ml compute create --name lab2-cluster --type AmlCompute
            # --tier LowPriority --size Standard_DS3_v2 --min-instances 0 --max-instances 4`.
            # Low-priority is a property of the CLUSTER, not the job — you cannot flip a
            # job onto discounted compute without a cluster already provisioned that way.
            compute="lab2-cluster",
            resources=JobResourceConfiguration(instance_count=1),
            environment_variables={
                "BLOB_URI": self.cfg.blob_uri,
                "MLFLOW_TRACKING_URI": "file:./mlruns",
            },
            display_name="itcs355-lab2-trial",
            experiment_name="itcs355-lab2",
            tags=self.cfg.tags(2),
        )
 
        submitted = ml_client.jobs.create_or_update(job)
        return submitted.name
 
    def wait_training(self, job_id: str) -> dict[str, Any]:
        """Poll until the job reaches a terminal state, then return what mattered.
 
        The handout warns you will hit a permissions error on your FIRST submission,
        and that it is normal. That error surfaces here, on the first `jobs.get` or
        `jobs.stream` call — read it, fix the one missing role, and write down which
        role it was. Drill 2 asks.
        """
        ml_client = self._ml_client()
        terminal = {"Completed", "Failed", "Canceled"}
 
        status = None
        while status not in terminal:
            job = ml_client.jobs.get(job_id)
            status = job.status
            time.sleep(15)
 
        if status != "Completed":
            raise RuntimeError(f"training job {job_id} ended with status={status}")
 
        return {
            "job_id": job_id,
            "status": status,
            "studio_url": job.studio_url,
            # Azure ML jobs write outputs under azureml://.../outputs/ by convention;
            # your train.py wrote metrics.json there via --metrics-out.
            "output_uri": f"azureml://jobs/{job_id}/outputs/artifacts/paths/outputs/",
        }
    
    # submit_training / register_model  -> Lab 2 (Azure ML command job + model registry)
    # deploy / invoke                   -> Lab 3 (managed online endpoint + deployment)
    # emit_metric                       -> Lab 4 (Azure Monitor custom metric)
    # generate                          -> Lab 5 (managed LLM endpoint; read the usage block for tokens)
    # teardown                          -> Lab 5 (resource graph query by tag)
