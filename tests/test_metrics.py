"""Lab 4 — the service exposes the signals the dashboard and the SLO depend on."""
from __future__ import annotations

import pytest

pytest.importorskip("fastapi")
from tests.test_service import VALID, client  # noqa: E402,F401  (reuse the fixture)


def _metric(text: str, prefix: str) -> list[str]:
    return [line for line in text.splitlines() if line.startswith(prefix)]


def test_metrics_endpoint_exposes_required_signals(client):  # noqa: F811
    client.post("/predict", json=VALID)
    body = client.get("/metrics").text
    assert _metric(body, "http_requests_total{"), "request counter missing"
    assert _metric(body, "request_latency_ms_bucket{"), "latency histogram missing"
    assert _metric(body, 'model_version_info{version="test-1"}'), "model version gauge missing"
    assert _metric(body, "feature_rolling_mean{"), "feature-distribution statistic missing"


def test_client_errors_are_counted_as_4xx_not_5xx(client):  # noqa: F811
    assert client.post("/predict", json={"temp_c": "not-a-number"}).status_code == 422
    body = client.get("/metrics").text
    assert any('status_class="4xx"' in line for line in _metric(body, "http_requests_total{"))


def test_rolling_mean_tracks_inputs(client):  # noqa: F811
    for _ in range(5):
        client.post("/predict", json={**VALID, "temp_c": 100.0})
    body = client.get("/metrics").text
    line = _metric(body, 'feature_rolling_mean{feature="temp_c"}')[0]
    assert float(line.split()[-1]) > VALID["temp_c"]  # window mean moved toward 100
