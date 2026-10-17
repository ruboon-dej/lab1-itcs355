"""Azure OpenAI chat call for AzureAdapter.generate. Standard library only (no openai SDK).

Environment (never committed):
  AZURE_OPENAI_ENDPOINT     https://<account>.openai.azure.com/
  AZURE_OPENAI_API_KEY      export it from `az cognitiveservices account keys list`
  AZURE_OPENAI_DEPLOYMENT   deployment name (default triage-llm)

Token counts come from the response's own usage block. Nothing here estimates tokens.
"""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from typing import Any

API_VERSION = "2024-10-21"


def generate(cfg, prompt: str, params: dict[str, Any]) -> dict[str, Any]:
    endpoint = os.environ["AZURE_OPENAI_ENDPOINT"].rstrip("/")
    key = os.environ["AZURE_OPENAI_API_KEY"]
    deployment = os.environ.get("AZURE_OPENAI_DEPLOYMENT", "triage-llm")
    url = f"{endpoint}/openai/deployments/{deployment}/chat/completions?api-version={API_VERSION}"

    messages = []
    if params.get("system"):
        messages.append({"role": "system", "content": params["system"]})
    messages.append({"role": "user", "content": prompt})
    body = {
        "messages": messages,
        "max_tokens": int(params.get("max_output_tokens", 200)),
        "temperature": float(params.get("temperature", 0.0)),
    }
    if params.get("seed") is not None:
        body["seed"] = int(params["seed"])
    data = json.dumps(body).encode()

    last_error = ""
    for attempt in range(5):
        req = urllib.request.Request(url, data=data, method="POST",
                                     headers={"api-key": key, "Content-Type": "application/json"})
        started = time.perf_counter()
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                payload = json.loads(resp.read())
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode(errors="replace")[:300]
            last_error = f"HTTP {exc.code}: {detail}"
            if exc.code in (429, 500, 502, 503):
                time.sleep(float(exc.headers.get("Retry-After", 2 * (attempt + 1))))
                continue
            raise RuntimeError(last_error) from exc
        latency_ms = int((time.perf_counter() - started) * 1000)
        usage = payload.get("usage", {})
        choice = payload["choices"][0]
        details = usage.get("prompt_tokens_details") or {}
        return {
            "response": choice["message"]["content"] or "",
            "input_tokens": int(usage["prompt_tokens"]),
            "output_tokens": int(usage["completion_tokens"]),
            "cached_input_tokens": int(details.get("cached_tokens", 0) or 0),
            "latency_ms": latency_ms,
            "model": payload.get("model", ""),
            "finish_reason": choice.get("finish_reason", ""),
        }
    raise RuntimeError(f"Azure OpenAI call failed after retries: {last_error}")
