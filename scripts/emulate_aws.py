"""Local stand-ins for AWS so the Lab 5 swap check can run without an AWS account.

    pip install boto3 "moto[server]" ; then in one terminal:  python scripts/emulate_aws.py

Starts (1) a moto S3 server on :5000 with the bucket created, and (2) a tiny stub that speaks
the SageMaker runtime wire protocol on :5001 (POST /endpoints/<name>/invocations).
This is an EMULATION and must be described as one in the write-up.
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

BUCKET = "itcs355-swap"


class Stub(BaseHTTPRequestHandler):
    def do_POST(self):  # noqa: N802
        if self.path.startswith("/endpoints/") and self.path.endswith("/invocations"):
            length = int(self.headers.get("Content-Length", 0))
            self.rfile.read(length)
            body = json.dumps({"predictions": [{"score": 0.0335}]}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, *args):  # keep the terminal quiet
        pass


def main() -> None:
    moto = subprocess.Popen([sys.executable, "-m", "moto.server", "-p", "5000"],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(3)
    import os
    os.environ.setdefault("AWS_ACCESS_KEY_ID", "test")
    os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "test")
    import boto3
    boto3.client("s3", endpoint_url="http://127.0.0.1:5000", region_name="ap-northeast-1") \
        .create_bucket(Bucket=BUCKET, CreateBucketConfiguration={"LocationConstraint": "ap-northeast-1"})
    print(f"S3 emulator on :5000 with bucket {BUCKET}; SageMaker stub on :5001. Ctrl-C to stop.")
    try:
        HTTPServer(("127.0.0.1", 5001), Stub).serve_forever()
    finally:
        moto.terminate()


if __name__ == "__main__":
    main()
