// ITCS355 Lab 3 — load test.
//
// Normal:
//   k6 run -e TARGET=https://<endpoint>/predict -e VUS=10 loadtest/k6.js
//
// Batch:
//   k6 run -e TARGET=https://<endpoint>/predict/batch -e VUS=10 -e BATCH=true -e BATCH_SIZE=100 loadtest/k6.js

import http from 'k6/http';
import { check } from 'k6';
import { Trend, Rate } from 'k6/metrics';

const latency = new Trend('predict_latency_ms');
const failures = new Rate('predict_failures');

export const options = {
  vus: Number(__ENV.VUS || 10),
  duration: __ENV.DURATION || '60s',

  summaryTrendStats: [
    'avg',
    'min',
    'med',
    'max',
    'p(90)',
    'p(95)',
    'p(99)',
  ],

  thresholds: {
    // Pre-declared p95 target: <200 ms.
    'predict_latency_ms': ['p(95)<200'],
    'predict_failures': ['rate<0.01'],
  },
};

const headers = {
  'Content-Type': 'application/json',
  'Authorization': `Bearer ${__ENV.AZURE_ENDPOINT_KEY}`,
};

function samplePayload() {
  return {
    temp_c: 78.4,
    vibration_mm_s: 3.1,
    pressure_kpa: 315.2,
    hours_since_service: 4200,
    load_pct: 68.0,
    ambient_humidity: 55.0,
  };
}

function buildBody() {
  const batch = __ENV.BATCH === 'true';
  const size = Number(__ENV.BATCH_SIZE || 100);

  const body = batch
    ? JSON.stringify({
        rows: Array.from({ length: size }, samplePayload),
      })
    : JSON.stringify(samplePayload());

  const payloadKb = Number(__ENV.PAYLOAD_KB || 0);

  if (payloadKb <= 0) {
    return body;
  }

  const targetBytes = payloadKb * 1024;

  if (body.length >= targetBytes) {
    return body;
  }

  const paddingBytes = targetBytes - body.length;
  const padding = 'x'.repeat(Math.max(0, paddingBytes));

  return body.slice(0, -1) + `,"padding":"${padding}"}`;
}

export default function () {
  const body = buildBody();

  const res = http.post(__ENV.TARGET, body, { headers });

  const success = res.status === 200;

  if (success) {
    latency.add(res.timings.duration);
  }

  failures.add(!success);

  check(res, {
    'status is 200': (r) => r.status === 200,
    'version reported': (r) =>
      r.status === 200 && r.headers['X-Model-Version'] !== undefined,
  });
}