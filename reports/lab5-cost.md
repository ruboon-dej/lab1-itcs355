# Lab 5 — Cost report

Provider `azure` · instance `Standard_DS2_v2` · 11.20 THB/hour

## 1. Estimate, made before running
25.00 THB

## 2. Actual, from billing filtered by tag
22.00 THB

## 3. The gap
-3.00 THB (-12.0%)

TODO(Lab 5): explain it. There is always a gap. The usual causes: the meter ran while you
debugged a broken job; storage and egress were left out of the estimate; the endpoint
stayed warm overnight; the instance was larger than planned. Name yours.

## 4. Breakdown by component
| Component | THB | Notes |
|---|---|---|
| Training | | |
| Storage | | |
| Serving | | |
| Pipeline | | |
| Monitoring | | |

TODO(Lab 5): fill from billing, split by tag.

## 5. Cost per 1,000 predictions
Measured throughput: 58.3 req/s

| Utilisation | THB per 1,000 |
|---|---|
| 5% | 1.0663 |
| 25% | 0.2133 |
| 80% | 0.0666 |

Utilisation is the most fragile number here, which is why three are reported rather than
one. State which you believe and why.

Below roughly **0.0030 req/s**, scheduled batch inference is cheaper than keeping
this endpoint warm. TODO(Lab 5): check that against your actual request rate. The answer
is usually lower than students expect.

## 6. One optimisation you applied
| | Before | After |
|---|---|---|
| Configuration | | |
| THB per 1,000 | | |
| Latency p95 | | |

TODO(Lab 5): candidates — right-size the instance, move to a scale-to-zero service, batch
where latency allows, cache repeated inputs, use spot for training, shorten log retention.
Report the latency cost as well as the money saved. An optimisation that halves cost and
triples p99 is a trade, not a win.
