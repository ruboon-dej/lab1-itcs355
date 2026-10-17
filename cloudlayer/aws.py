"""AWS adapter: the three methods the Lab 5 portability swap needs (upload, download, invoke).

BLOB_URI looks like s3://bucket/prefix. Nothing here is called with an endpoint override:
to run against an emulator, export AWS_ENDPOINT_URL_S3 / AWS_ENDPOINT_URL_SAGEMAKER_RUNTIME
(boto3 reads them), so this file stays identical for a real account.

Everything else raises NotImplementedError on purpose: this is a seam test, not a migration.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from cloudlayer.base import CloudAdapter


def _split(uri: str) -> tuple[str, str]:
    parsed = urlparse(uri)
    if parsed.scheme != "s3" or not parsed.netloc:
        raise ValueError(f"expected an s3://bucket/key URI, got {uri!r}")
    return parsed.netloc, parsed.path.lstrip("/")


class AwsAdapter(CloudAdapter):
    def _s3(self):
        import boto3

        return boto3.client("s3", region_name=self.cfg.region if self.cfg.region != "unset" else None)

    def upload(self, local_path: str, key: str) -> str:
        bucket, prefix = _split(self.cfg.blob_uri)
        full_key = "/".join(p for p in (prefix.strip("/"), key.lstrip("/")) if p)
        self._s3().upload_file(local_path, bucket, full_key)
        return f"s3://{bucket}/{full_key}"

    def download(self, uri: str, local_path: str) -> None:
        bucket, key = _split(uri)
        Path(local_path).parent.mkdir(parents=True, exist_ok=True)
        self._s3().download_file(bucket, key, local_path)

    def invoke(self, endpoint: str, payload: dict[str, Any]) -> dict[str, Any]:
        """SageMaker real-time endpoint. The response body is a stream of bytes whose shape
        is whatever the container chose; Azure returns parsed JSON with `probability`.
        Normalising the two is the leak this lab asks you to write about."""
        import boto3

        client = boto3.client("sagemaker-runtime",
                              region_name=self.cfg.region if self.cfg.region != "unset" else None)
        resp = client.invoke_endpoint(EndpointName=endpoint, ContentType="application/json",
                                      Body=json.dumps(payload))
        body = json.loads(resp["Body"].read())
        if "probability" in body:
            return body
        preds = body.get("predictions") or []
        if preds and "score" in preds[0]:
            return {"probability": float(preds[0]["score"]), "model_version": "unknown"}
        return body

    def push_image(self, local_tag: str) -> str:
        raise NotImplementedError("not part of the Lab 5 swap: push_image")
