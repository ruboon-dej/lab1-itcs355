"""Azure adapter.
Implements Azure-specific operations for the MLOps labs.

Lab 1:
    - Blob upload/download
    - Container Registry image push

Lab 2:
    - Azure ML training jobs
    - MLflow/model registration

Lab 3:
    - Azure Container Apps deployment
    - Canary revisions
    - Traffic splitting
    - Inference

Lab 4:
    - Azure Monitor metrics

Lab 5:
    - Managed LLM endpoint usage

SDKs:
    pip install azure-storage-blob azure-identity azure-containerregistry
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from azure.ai.ml import Input, MLClient, Output, command
from azure.ai.ml.constants import AssetTypes
from azure.ai.ml.entities import Environment, Model
from azure.core.exceptions import HttpResponseError
from azure.identity import DefaultAzureCredential

from cloudlayer.base import CloudAdapter


def _parse_blob_uri(blob_uri: str) -> tuple[str, str, str]:
    """Parse a Blob Storage URI.

    Supported form:

        https://<account>.blob.core.windows.net/<container>/<prefix>

    Also accepts:

        abfss://<container>@<account>.dfs.core.windows.net/<prefix>

    Returns:

        (account, container, prefix)
    """

    parsed = urlparse(blob_uri)

    # HTTPS Blob Storage URI.
    if parsed.scheme == "https":
        if not parsed.netloc.endswith(".blob.core.windows.net"):
            raise ValueError(
                f"Unsupported Blob Storage URI: {blob_uri}"
            )

        account = parsed.netloc.split(".")[0]

        parts = parsed.path.strip("/").split("/", 1)

        if not parts or not parts[0]:
            raise ValueError(
                f"Blob URI is missing the container name: {blob_uri}"
            )

        container = parts[0]
        prefix = parts[1] if len(parts) > 1 else ""

        return account, container, prefix

    # ADLS Gen2 / ABFSS URI.
    if parsed.scheme == "abfss":
        if "@" not in parsed.netloc:
            raise ValueError(
                f"Invalid ABFSS URI: {blob_uri}"
            )

        container, account_host = parsed.netloc.split("@", 1)

        if not account_host.endswith(".dfs.core.windows.net"):
            raise ValueError(
                f"Unsupported ABFSS account URI: {blob_uri}"
            )

        account = account_host.split(".")[0]
        prefix = parsed.path.strip("/")

        return account, container, prefix

    raise ValueError(
        f"Unsupported Blob Storage URI scheme: {parsed.scheme!r}. "
        "Expected https or abfss."
    )


class AzureAdapter(CloudAdapter):

    def set_traffic(
        self,
        endpoint: str,
        traffic: dict[str, int],
    ) -> None:
        """Set Azure Container Apps revision traffic."""

        resource_group = os.environ["AZURE_RESOURCE_GROUP"]

        revision_weights = [
            f"{revision}={weight}"
            for revision, weight in traffic.items()
        ]

        subprocess.run(
            [
                "az",
                "containerapp",
                "ingress",
                "traffic",
                "set",
                "--name",
                endpoint,
                "--resource-group",
                resource_group,
                "--revision-weight",
                *revision_weights,
            ],
            check=True,
        )

    # ------------------------------------------------------------------
    # Lab 2: Azure ML model registration
    # ------------------------------------------------------------------

    def register_model(
        self,
        model_uri: str,
        name: str,
        tags: dict[str, str] | None = None,
    ) -> str:
        """Register a model in Azure ML.

        If model_uri is an MLflow runs:/ URI, Azure ML preserves lineage
        back to the MLflow run.

        Otherwise, model_uri must point to a local model artifact.
        """

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
            description=(
                "ITCS355 Lab 2 selected RandomForest model"
            ),
            tags=tags or {},
        )

        registered = ml_client.models.create_or_update(model)

        print(
            f"Registered model: {registered.name}, "
            f"version: {registered.version}"
        )

        return str(registered.version)

    # ------------------------------------------------------------------
    # Lab 1: Azure Blob Storage
    # ------------------------------------------------------------------

    def _blob_service_client(self):
        from azure.storage.blob import BlobServiceClient

        account, _, _ = _parse_blob_uri(
            self.cfg.blob_uri
        )

        account_url = (
            f"https://{account}.blob.core.windows.net"
        )

        return BlobServiceClient(
            account_url=account_url,
            credential=DefaultAzureCredential(),
        )

    def upload(
        self,
        local_path: str,
        key: str,
    ) -> str:
        """Upload a local file to Azure Blob Storage."""

        account, container, prefix = _parse_blob_uri(
            self.cfg.blob_uri
        )

        blob_name = (
            f"{prefix}/{key}".strip("/")
            if prefix
            else key
        )

        client = self._blob_service_client()

        blob_client = client.get_blob_client(
            container=container,
            blob=blob_name,
        )

        with open(local_path, "rb") as f:
            blob_client.upload_blob(
                f,
                overwrite=True,
            )

        return (
            f"https://{account}.blob.core.windows.net/"
            f"{container}/{blob_name}"
        )

    def download(
        self,
        uri: str,
        local_path: str,
    ) -> None:
        """Download a Blob Storage object to a local file."""

        parsed = urlparse(uri)

        parts = parsed.path.strip("/").split("/", 1)

        if len(parts) != 2:
            raise ValueError(
                f"Invalid Blob Storage URI: {uri}"
            )

        container, blob_name = parts

        client = self._blob_service_client()

        blob_client = client.get_blob_client(
            container=container,
            blob=blob_name,
        )

        Path(local_path).parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        with open(local_path, "wb") as f:
            f.write(
                blob_client.download_blob().readall()
            )

    # ------------------------------------------------------------------
    # Lab 1: Azure Container Registry
    # ------------------------------------------------------------------

    def push_image(
        self,
        local_tag: str,
    ) -> str:
        """Push a Docker image to ACR and return its immutable digest URI."""

        registry_host, repo = (
            self.cfg.container_registry.split("/", 1)
        )

        image_tag = local_tag.rsplit(":", 1)[-1]

        remote_tag = (
            f"{registry_host}/{repo}:{image_tag}"
        )

        subprocess.run(
            [
                "docker",
                "tag",
                local_tag,
                remote_tag,
            ],
            check=True,
        )

        push_result = subprocess.run(
            [
                "docker",
                "push",
                remote_tag,
            ],
            check=True,
            capture_output=True,
            text=True,
        )

        # Docker normally reports the digest as:
        #
        #   digest: sha256:<hash>
        #
        # Search both stdout and stderr because Docker CLI output can
        # vary depending on the environment.
        push_output = (
            f"{push_result.stdout}\n"
            f"{push_result.stderr}"
        )

        match = re.search(
            r"digest:\s*(sha256:[0-9a-f]+)",
            push_output,
        )

        if not match:
            raise RuntimeError(
                "Could not parse image digest from docker push output:\n"
                f"{push_output}"
            )

        digest = match.group(1)

        return (
            f"{registry_host}/{repo}@{digest}"
        )

    # ------------------------------------------------------------------
    # Azure ML helpers
    # ------------------------------------------------------------------

    def _ml_client(self) -> MLClient:
        """Create an Azure ML client using DefaultAzureCredential."""

        return MLClient(
            credential=DefaultAzureCredential(),
            subscription_id=os.environ[
                "AZURE_SUBSCRIPTION_ID"
            ],
            resource_group_name=os.environ[
                "AZURE_RESOURCE_GROUP"
            ],
            workspace_name=os.environ[
                "AZURE_ML_WORKSPACE"
            ],
        )

    def _mlflow_tracking_uri(self) -> str:
        """Return the workspace MLflow tracking URI."""

        return (
            self._ml_client()
            .workspaces
            .get(
                os.environ["AZURE_ML_WORKSPACE"]
            )
            .mlflow_tracking_uri
        )

    # ------------------------------------------------------------------
    # Lab 2: Azure ML training
    # ------------------------------------------------------------------

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

        compute = ml_client.compute.get(
            compute_name
        )

        tier = str(
            getattr(
                compute,
                "tier",
                getattr(
                    getattr(
                        compute,
                        "properties",
                        None,
                    ),
                    "vm_priority",
                    "",
                ),
            )
        ).lower().replace("-", "_")

        if tier not in {
            "low_priority",
            "lowpriority",
        }:
            raise RuntimeError(
                f"Lab 2 requires discounted compute, but compute "
                f"{compute_name!r} reports tier={tier!r}. "
                "Do not submit the study on Dedicated compute."
            )

        cli_args = " ".join(
            f"--{key} {value}"
            for key, value in args.items()
        )

        env = Environment(
            image=image_uri
        )

        data_uri = (
            f"{self.cfg.blob_uri.rstrip('/')}"
            "/training-data/sensors.csv"
        )

        output_uri = (
            f"{self.cfg.blob_uri.rstrip('/')}"
            f"/lab2-outputs/{uuid.uuid4().hex}"
        )

        git_sha = subprocess.run(
            [
                "git",
                "rev-parse",
                "HEAD",
            ],
            capture_output=True,
            text=True,
            check=True,
            cwd=self.cfg.data_dir.parent,
        ).stdout.strip()

        dvc_text = (
            self.cfg.data_dir.parent
            / "data"
            / "raw.dvc"
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

        tracking_uri = (
            self._mlflow_tracking_uri()
        )

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
                "--metrics-out "
                f"${{{{outputs.model_output}}}}/metrics.json"
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

        submitted = (
            ml_client.jobs.create_or_update(job)
        )

        return submitted.name

    def wait_training(
        self,
        job_id: str,
    ) -> dict[str, Any]:
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
            "mlflow_run_id": metrics[
                "mlflow_run_id"
            ],
            "data_fingerprint": metrics[
                "data_fingerprint"
            ],
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
            "val_roc_auc": metrics[
                "val_roc_auc"
            ],
            "val_pr_auc": metrics[
                "val_pr_auc"
            ],
            "test_roc_auc": metrics[
                "test_roc_auc"
            ],
            "test_pr_auc": metrics[
                "test_pr_auc"
            ],
            "training_duration_s": metrics.get(
                "training_duration_s"
            ),
            "metrics": metrics,
        }

    # ------------------------------------------------------------------
    # Lab 3: Container Apps ACR authentication
    # ------------------------------------------------------------------

    def _ensure_acr_auth(
        self,
        endpoint: str,
        resource_group: str,
    ) -> None:
        """Configure ACR authentication for Container Apps."""

        acr_name = self.cfg.container_registry.split("/", 1)[0]

        subprocess.run(
            [
                "az",
                "acr",
                "update",
                "--name",
                acr_name,
                "--resource-group",
                resource_group,
                "--admin-enabled",
                "true",
            ],
            check=True,
        )

        acr_login_server = subprocess.run(
            [
                "az",
                "acr",
                "show",
                "--name",
                acr_name,
                "--resource-group",
                resource_group,
                "--query",
                "loginServer",
                "--output",
                "tsv",
            ],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()

        acr_username = subprocess.run(
            [
                "az",
                "acr",
                "credential",
                "show",
                "--name",
                acr_name,
                "--resource-group",
                resource_group,
                "--query",
                "username",
                "--output",
                "tsv",
            ],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()

        acr_password = subprocess.run(
            [
                "az",
                "acr",
                "credential",
                "show",
                "--name",
                acr_name,
                "--resource-group",
                resource_group,
                "--query",
                "passwords[0].value",
                "--output",
                "tsv",
            ],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()

        if not acr_login_server or not acr_username or not acr_password:
            raise RuntimeError("Could not retrieve ACR credentials")

        subprocess.run(
            [
                "az",
                "containerapp",
                "secret",
                "set",
                "--name",
                endpoint,
                "--resource-group",
                resource_group,
                "--secrets",
                f"acr-pwd={acr_password}",
            ],
            check=True,
        )

        subprocess.run(
            [
                "az",
                "containerapp",
                "registry",
                "set",
                "--name",
                endpoint,
                "--resource-group",
                resource_group,
                "--server",
                acr_login_server,
                "--username",
                acr_username,
                "--password",
                "secretref:acr-pwd",
            ],
            check=True,
        )

    # ------------------------------------------------------------------
    # Lab 3: Container Apps deployment
    # ------------------------------------------------------------------

    def _download_registered_model(
        self,
        model_name: str,
        model_version: str,
    ) -> str:
        """Download a registered Azure ML model and return its local path."""

        ml_client = self._ml_client()

        model = ml_client.models.get(
            name=model_name,
            version=model_version,
        )

        download_dir = Path(
            tempfile.mkdtemp(prefix="itcs355-model-")
        )

        downloaded = ml_client.models.download(
            name=model_name,
            version=model_version,
            download_path=str(download_dir),
        )

        downloaded_path = Path(downloaded)

        if downloaded_path.is_file():
            return str(downloaded_path)

        candidates = list(
            download_dir.rglob("model.joblib")
        )

        if not candidates:
            raise RuntimeError(
                f"Registered model {model_name}:{model_version} "
                "did not contain model.joblib"
            )

        return str(candidates[0])

    def deploy(
        self,
        model_ref: str,
        endpoint: str,
        instance: str,
    ) -> str:
        """Deploy the serving image to Azure Container Apps."""

        if ":" in model_ref:
            model_name, model_version = (
                model_ref.rsplit(":", 1)
            )
        else:
            model_name = (
                self.cfg.model_registry_name
            )
            model_version = model_ref

        image_tag = os.environ.get(
            "SERVE_IMAGE_TAG",
            "itcs355-serve:latest",
        )

        if ":" not in image_tag:
            image_tag = (
                f"itcs355-serve:{image_tag}"
            )

        # Push the serving image and obtain its immutable digest.
        image_uri = self.push_image(
            image_tag
        )

        resource_group = os.environ[
            "AZURE_RESOURCE_GROUP"
        ]

        environment = os.environ.get(
            "AZURE_CONTAINERAPPS_ENVIRONMENT",
            f"itcs355-{self.cfg.project_id}-cae",
        )

        # Check whether the Container App already exists.
        exists = subprocess.run(
            [
                "az",
                "containerapp",
                "show",
                "--name",
                endpoint,
                "--resource-group",
                resource_group,
            ],
            capture_output=True,
            text=True,
        )

        if exists.returncode != 0:
            # ----------------------------------------------------------
            # First deployment
            # ----------------------------------------------------------

            # Start with a public image so creation does not depend
            # on private ACR authentication already being configured.
            subprocess.run(
                [
                    "az",
                    "containerapp",
                    "create",
                    "--name",
                    endpoint,
                    "--resource-group",
                    resource_group,
                    "--environment",
                    environment,
                    "--image",
                    "mcr.microsoft.com/"
                    "azuredocs/containerapps-helloworld:latest",
                    "--target-port",
                    "8080",
                    "--ingress",
                    "external",
                    "--min-replicas",
                    "0",
                    "--max-replicas",
                    "1",
                    "--cpu",
                    "0.5",
                    "--memory",
                    "1.0Gi",
                    "--env-vars",
                    f"MODEL_VERSION={model_version}",
                    f"MODEL_REGISTRY_NAME={model_name}",
                    "MODEL_PATH=/app/model/model.joblib",
                ],
                check=True,
            )

            # Configure ACR authentication.
            self._ensure_acr_auth(
                endpoint,
                resource_group,
            )

            # Replace the temporary public image with the immutable
            # private ACR image.
            subprocess.run(
                [
                    "az",
                    "containerapp",
                    "update",
                    "--name",
                    endpoint,
                    "--resource-group",
                    resource_group,
                    "--image",
                    image_uri,
                    "--set-env-vars",
                    f"MODEL_VERSION={model_version}",
                    f"MODEL_REGISTRY_NAME={model_name}",
                    "MODEL_PATH=/app/model/model.joblib",
                ],
                check=True,
            )

        else:
            # ----------------------------------------------------------
            # Existing Container App
            # ----------------------------------------------------------

            # Re-assert ACR authentication before updating the image.
            self._ensure_acr_auth(
                endpoint,
                resource_group,
            )

            subprocess.run(
                [
                    "az",
                    "containerapp",
                    "update",
                    "--name",
                    endpoint,
                    "--resource-group",
                    resource_group,
                    "--image",
                    image_uri,
                    "--cpu",
                    "0.5",
                    "--memory",
                    "1.0Gi",
                    "--min-replicas",
                    "0",
                    "--max-replicas",
                    "1",
                    "--set-env-vars",
                    f"MODEL_VERSION={model_version}",
                    f"MODEL_REGISTRY_NAME={model_name}",
                    "MODEL_PATH=/app/model/model.joblib",
                ],
                check=True,
            )

        # Find the revision created by the deployment.
        revision_name = subprocess.run(
            [
                "az",
                "containerapp",
                "show",
                "--name",
                endpoint,
                "--resource-group",
                resource_group,
                "--query",
                "properties.latestRevisionName",
                "--output",
                "tsv",
            ],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()

        if not revision_name:
            raise RuntimeError(
                f"Could not determine latest revision "
                f"for Container App {endpoint!r}"
            )


        print(
            f"Container App deployed: {endpoint} "
            f"(revision={revision_name}, "
            f"model={model_name}:{model_version})"
        )

        return endpoint

    # ------------------------------------------------------------------
    # Lab 3: Canary deployment
    # ------------------------------------------------------------------

    def deploy_canary(
        self,
        model_ref: str,
        endpoint: str,
        instance: str,
    ) -> str:
        """Deploy a second model as a Container Apps revision."""

        if ":" in model_ref:
            model_name, model_version = (
                model_ref.rsplit(":", 1)
            )
        else:
            model_name = (
                self.cfg.model_registry_name
            )
            model_version = model_ref

        image_tag = os.environ.get(
            "SERVE_IMAGE_TAG",
            "itcs355-serve:latest",
        )

        if ":" not in image_tag:
            image_tag = (
                f"itcs355-serve:{image_tag}"
            )

        image_uri = self.push_image(
            image_tag
        )

        resource_group = os.environ[
            "AZURE_RESOURCE_GROUP"
        ]

        # Ensure the existing app can pull from ACR.
        self._ensure_acr_auth(
            endpoint,
            resource_group,
        )

        # Canary deployments require multiple active revisions.
        # In Single mode, `az containerapp update` replaces the
        # existing revision instead of creating a separate canary.
        subprocess.run(
            [
                "az",
                "containerapp",
                "revision",
                "set-mode",
                "--name",
                endpoint,
                "--resource-group",
                resource_group,
                "--mode",
                "multiple",
            ],
            check=True,
        )

        # Create the new revision.
        subprocess.run(
            [
                "az",
                "containerapp",
                "update",
                "--name",
                endpoint,
                "--resource-group",
                resource_group,
                "--image",
                image_uri,
                "--set-env-vars",
                f"MODEL_VERSION={model_version}",
                f"MODEL_REGISTRY_NAME={model_name}",
            ],
            check=True,
        )

        # Determine the new revision name.
        revision_name = subprocess.run(
            [
                "az",
                "containerapp",
                "show",
                "--name",
                endpoint,
                "--resource-group",
                resource_group,
                "--query",
                "properties.latestRevisionName",
                "--output",
                "tsv",
            ],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()

        if not revision_name:
            raise RuntimeError(
                f"Could not determine canary revision "
                f"for Container App {endpoint!r}"
            )

        print(
            f"Container App canary revision created for "
            f"{model_name}:{model_version} "
            f"(revision={revision_name})"
        )

        # The caller can use set_traffic() to split traffic,
        # for example 90/10.
        return revision_name

    # ------------------------------------------------------------------
    # Lab 3: Inference
    # ------------------------------------------------------------------

    def invoke(
        self,
        endpoint: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        """Invoke the Azure Container Apps inference endpoint."""

        resource_group = os.environ[
            "AZURE_RESOURCE_GROUP"
        ]

        fqdn = subprocess.run(
            [
                "az",
                "containerapp",
                "show",
                "--name",
                endpoint,
                "--resource-group",
                resource_group,
                "--query",
                "properties.configuration.ingress.fqdn",
                "--output",
                "tsv",
            ],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()

        if not fqdn:
            raise RuntimeError(
                f"Container App {endpoint!r} has no "
                "public ingress FQDN."
            )

        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".json",
            delete=False,
        ) as request_file:
            json.dump(
                payload,
                request_file,
            )
            request_path = request_file.name

        try:
            last_exc: Exception | None = None

            # Container Apps can scale to zero. Retry while the
            # revision is cold-starting.
            for attempt, wait_s in enumerate(
                [0, 3, 6, 10, 15, 20],
                start=1,
            ):
                if wait_s:
                    time.sleep(wait_s)

                try:
                    response = subprocess.run(
                        [
                            "curl",
                            "--fail",
                            "--silent",
                            "--show-error",
                            "--max-time",
                            "20",
                            "-X",
                            "POST",
                            f"https://{fqdn}/predict",
                            "-H",
                            "Content-Type: application/json",
                            "--data-binary",
                            f"@{request_path}",
                        ],
                        check=True,
                        capture_output=True,
                        text=True,
                    )

                    return json.loads(
                        response.stdout
                    )

                except subprocess.CalledProcessError as exc:
                    last_exc = exc

                    print(
                        f"invoke attempt {attempt} failed "
                        f"(cold start / not ready yet): "
                        f"{exc.stderr.strip()}"
                    )

            raise RuntimeError(
                f"Container App {endpoint!r} did not "
                "become ready after retries"
            ) from last_exc

        finally:
            Path(request_path).unlink(
                missing_ok=True
            )

    # ------------------------------------------------------------------
    # Lab 2/3: Teardown
    # ------------------------------------------------------------------

    # --- Lab 4 ---------------------------------------------------------------
    def emit_metric(self, name: str, value: float, unit: str = "None") -> None:
        """Send one custom metric to Application Insights (Azure Monitor).

        Posts straight to the ingestion endpoint named in
        APPLICATIONINSIGHTS_CONNECTION_STRING and CHECKS Azure's reply, so a scheduled job needs
        no Azure login and a failed delivery raises instead of passing silently. (The first
        version used the OpenTelemetry exporter, which reports success even when nothing arrives.)
        The metric shows up in Log Analytics under `customMetrics`.
        """
        import datetime
        import requests

        conn = os.environ.get("APPLICATIONINSIGHTS_CONNECTION_STRING", "").strip()
        if not conn:
            raise RuntimeError(
                "Set APPLICATIONINSIGHTS_CONNECTION_STRING to emit metrics to Azure Monitor."
            )
        parts = dict(p.split("=", 1) for p in conn.split(";") if "=" in p)
        ikey = parts.get("InstrumentationKey", "").strip()
        endpoint = parts.get("IngestionEndpoint", "https://dc.services.visualstudio.com").strip()
        if not ikey:
            raise RuntimeError("the connection string has no InstrumentationKey")
        envelope = {
            "name": "Microsoft.ApplicationInsights.Metric",
            "time": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "iKey": ikey,
            "data": {
                "baseType": "MetricData",
                "baseData": {"ver": 2, "metrics": [{"name": name, "value": float(value)}]},
            },
        }
        response = requests.post(endpoint.rstrip("/") + "/v2/track", json=[envelope], timeout=15)
        try:
            body = response.json()
        except ValueError:
            body = {}
        if response.status_code != 200 or body.get("itemsAccepted") != 1:
            raise RuntimeError(
                f"Application Insights did not accept the metric: HTTP {response.status_code} {body}"
            )

    def teardown(
        self,
        tags: dict[str, str],
    ) -> list[str]:
        """Delete Azure ML jobs and compute resources carrying the tags."""

        ml_client = self._ml_client()

        deleted: list[str] = []

        # --------------------------------------------------------------
        # Azure ML jobs
        # --------------------------------------------------------------

        for job in ml_client.jobs.list():
            job_tags = getattr(
                job,
                "tags",
                {},
            ) or {}

            if all(
                job_tags.get(key) == value
                for key, value in tags.items()
            ):
                try:
                    ml_client.jobs.begin_delete(
                        job.name
                    )

                    deleted.append(
                        f"job:{job.name}"
                    )

                except HttpResponseError as exc:
                    if exc.status_code != 404:
                        raise

        # --------------------------------------------------------------
        # Azure ML compute
        # --------------------------------------------------------------

        for compute in ml_client.compute.list():
            compute_tags = getattr(
                compute,
                "tags",
                {},
            ) or {}

            if all(
                compute_tags.get(key) == value
                for key, value in tags.items()
            ):
                ml_client.compute.begin_delete(
                    compute.name
                )

                deleted.append(
                    f"compute:{compute.name}"
                )

        # --------------------------------------------------------------
        # Azure Container App
        # --------------------------------------------------------------

        container_app_name = os.environ.get(
            "ENDPOINT_NAME",
            f"itcs355-{self.cfg.project_id}-predict",
        )

        resource_group = os.environ[
            "AZURE_RESOURCE_GROUP"
        ]

        result = subprocess.run(
            [
                "az",
                "containerapp",
                "show",
                "--name",
                container_app_name,
                "--resource-group",
                resource_group,
            ],
            capture_output=True,
            text=True,
        )

        if result.returncode == 0:
            subprocess.run(
                [
                    "az",
                    "containerapp",
                    "delete",
                    "--name",
                    container_app_name,
                    "--resource-group",
                    resource_group,
                    "--yes",
                ],
                check=True,
            )

            deleted.append(
                f"containerapp:{container_app_name}"
            )

        return deleted


# ----------------------------------------------------------------------
# Lab mapping
# ----------------------------------------------------------------------
#
# submit_training / wait_training / register_model
#     -> Lab 2
#
# deploy / deploy_canary / set_traffic / invoke
#     -> Lab 3
#
# emit_metric
#     -> Lab 4
#
# generate
#     -> Lab 5
#
# teardown
#     -> Labs 2/3