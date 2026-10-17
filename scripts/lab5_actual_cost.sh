#!/usr/bin/env bash
# Actual cost from Azure Cost Management, grouped by resource, filtered by tag lab=5.
# Usage: bash scripts/lab5_actual_cost.sh 2026-10-16 2026-10-22   (from, to; UTC dates)
# Billing lags 8-24 hours: run this at least a day after teardown. The registry predates
# the lab tag, so it is queried separately below.
set -euo pipefail
FROM="${1:?from date}"; TO="${2:?to date}"
SUB=$(az account show --query id -o tsv)
URL="https://management.azure.com/subscriptions/${SUB}/providers/Microsoft.CostManagement/query?api-version=2023-11-01"
q() {
  az rest --method post --url "$URL" --body "$1" \
    --query "properties.rows[].[to_string(@[0]), @[1], @[2]]" -o tsv 2>&1 || true
}
echo "=== tagged lab=5, by resource (columns: cost, resource id, currency)"
q "{\"type\":\"ActualCost\",\"timeframe\":\"Custom\",\"timePeriod\":{\"from\":\"${FROM}T00:00:00Z\",\"to\":\"${TO}T23:59:59Z\"},\"dataset\":{\"granularity\":\"None\",\"aggregation\":{\"totalCost\":{\"name\":\"Cost\",\"function\":\"Sum\"}},\"grouping\":[{\"type\":\"Dimension\",\"name\":\"ResourceId\"}],\"filter\":{\"Tags\":{\"Name\":\"lab\",\"Operator\":\"In\",\"Values\":[\"5\"]}}}}"
echo "=== whole resource group, by service"
q "{\"type\":\"ActualCost\",\"timeframe\":\"Custom\",\"timePeriod\":{\"from\":\"${FROM}T00:00:00Z\",\"to\":\"${TO}T23:59:59Z\"},\"dataset\":{\"granularity\":\"None\",\"aggregation\":{\"totalCost\":{\"name\":\"Cost\",\"function\":\"Sum\"}},\"grouping\":[{\"type\":\"Dimension\",\"name\":\"ServiceName\"}]}}"
