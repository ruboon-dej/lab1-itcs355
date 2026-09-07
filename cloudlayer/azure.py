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
from typing import Any
from urllib.parse import urlparse

from cloudlayer.base import CloudAdapter


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
    # submit_training / register_model  -> Lab 2 (Azure ML command job + model registry)
    # deploy / invoke                   -> Lab 3 (managed online endpoint + deployment)
    # emit_metric                       -> Lab 4 (Azure Monitor custom metric)
    # generate                          -> Lab 5 (managed LLM endpoint; read the usage block for tokens)
    # teardown                          -> Lab 5 (resource graph query by tag)
