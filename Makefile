# ITCS355 Lab 1
# `make reproduce` is the one command a grader runs. Keep it working.

SHELL := /bin/bash
IMAGE ?= itcs355-lab1
TAG   ?= $(shell git rev-parse --short HEAD 2>/dev/null || echo dev)
PLATFORM ?= linux/amd64
SEED ?= 20260101
VERSION ?= 2
CANARY_VERSION ?= 3

# Lab 3/5 reproducibility defaults
EST ?= 25
ACT ?= 22
RPS ?= 58.33
INSTANCE ?= Standard_DS2_v2
.DEFAULT_GOAL := help

.PHONY: help setup cloud-check data test portability-audit train image image-push reproduce verify clean teardown \
        tune tune-local compare reload-check serve serve-image serve-image-push deploy smoke loadtest drift inject-drift pipeline cost cost-report swap-check llm-eval llm-gate canary rollback

cost:
	@test -n "$(EST)" || (echo "ERROR: set EST, e.g. EST=25"; exit 1)
	@test -n "$(ACT)" || (echo "ERROR: set ACT, e.g. ACT=22"; exit 1)
	@test -n "$(RPS)" || (echo "ERROR: set RPS, e.g. RPS=58.33"; exit 1)
	@test -n "$(INSTANCE)" || (echo "ERROR: set INSTANCE, e.g. INSTANCE=Standard_DS2_v2"; exit 1)
	python scripts/cost_report.py --estimate "$(EST)" --actual "$(ACT)" --rps "$(RPS)" --instance "$(INSTANCE)"

cost-report: cost

help:
	@grep -E "^[a-zA-Z_-]+:.*?## .*$$" $(MAKEFILE_LIST) | awk -F":.*?## " "{printf \"  %-20s %s\\n\", \$$1, \$$2}"

setup: ## Install dependencies and print environment status
	python -m pip install --upgrade pip
	pip install -r requirements.txt
	@echo "environment ok"

cloud-check: ## Resolve the eight capability slots
	python scripts/cloud_check.py

data: ## Generate the default dataset (deterministic)
	python scripts/make_dataset.py --seed $(SEED)

test: ## Run data contract and split property tests
	pytest -q tests/

portability-audit: ## Fail if provider strings leak into src/
	python scripts/portability_audit.py

train: ## Train locally, outside the container
	python -m src.train --seed $(SEED) --metrics-out reports/metrics.json

image: ## Build the training image for linux/amd64
	docker buildx build --platform $(PLATFORM) -t $(IMAGE):$(TAG) --load .

image-push: image ## Push to CONTAINER_REGISTRY via your adapter
	@python -c "from cloudlayer.factory import get_adapter; from src import config; \
	uri = get_adapter(config.load()).push_image(\"$(IMAGE):$(TAG)\"); \
	open('.image_uri', 'w').write(uri); \
	print(uri)"

reproduce: data image ## THE ONE COMMAND. Grader runs this.
	docker run --rm \
	  -v "$$PWD/data:/app/data:ro" \
	  -v "$$PWD/reports:/app/reports" \
	  -e MLFLOW_TRACKING_URI=sqlite:////app/reports/mlflow.db \
	  $(IMAGE):$(TAG) --seed $(SEED) --metrics-out /app/reports/metrics.json

verify: ## Check the produced metric against the README claim
	python scripts/verify_metric.py

teardown: ## Delete every resource tagged course=itcs355 for this lab
	python -c "from src import config; from cloudlayer.factory import get_adapter; \
	cfg=config.load(); print(get_adapter(cfg).teardown(cfg.tags(3)))"

clean: ## Remove local artifacts
	rm -rf mlruns mlartifacts mlflow.db reports/metrics.json reports/deploy-model

# --- Lab 2 -------------------------------------------------------------------
tune: ## Budgeted hyperparameter study on managed compute
	python scripts/tune_remote.py --trials 12 --budget-thb 150

tune-local: ## Local Lab 2 development study; not valid evidence for submission
	python -m src.tune --trials 12 --budget-thb 150 --instance local

train-remote: ## Submit one trial as a managed Azure ML job
	python scripts/train_remote.py --n-estimators 200 --max-depth 8 --seed $(SEED)

compare: ## Rank runs by metric and by cost per point
	python scripts/compare_runs.py --experiment itcs355-lab2

reload-check: ## Load the registered model by version and score rows
	python scripts/reload_check.py --name $(MODEL_REGISTRY_NAME) --version $(VERSION)

# --- Lab 3 -------------------------------------------------------------------
serve: ## Run the inference service locally on :8080
	python scripts/export_model.py --out reports/model.joblib
	MODEL_PATH=reports/model.joblib MODEL_VERSION=local uvicorn service.app:app --port 8080

serve-image: ## Build the serving image
	az ml model download \
		--name $(MODEL_REGISTRY_NAME) \
		--version $(VERSION) \
		--resource-group $${AZURE_RESOURCE_GROUP} \
		--workspace-name $${AZURE_ML_WORKSPACE} \
		--download-path reports/deploy-model
	cp reports/deploy-model/$(MODEL_REGISTRY_NAME)/model.joblib reports/deploy-model/model.joblib
	docker buildx build \
		--platform $(PLATFORM) \
		-f service/Dockerfile.serve \
		-t itcs355-serve:$(TAG) \
		--load .

serve-image-push: serve-image ## Build and push the serving image to Azure Container Registry
	SERVE_IMAGE_TAG=$(TAG) python -c "from src.config import load; from cloudlayer.factory import get_adapter; cfg=load(); print(get_adapter(cfg).push_image('itcs355-serve:$(TAG)'))"

deploy: serve-image-push ## Deploy the registered model to Azure Container Apps
	SERVE_IMAGE_TAG=$(TAG) python -c "from src.config import load; from cloudlayer.factory import get_adapter; import os; cfg=load(); adapter=get_adapter(cfg); endpoint=os.environ.get('ENDPOINT_NAME', f'itcs355-{cfg.project_id}-predict'); print(adapter.deploy(f'{cfg.model_registry_name}:$(VERSION)', endpoint, 'Standard_DS2_v2'))"

smoke: ## Invoke the deployed endpoint once
	python -c "from src.config import load; from cloudlayer.factory import get_adapter; import os; cfg=load(); adapter=get_adapter(cfg); endpoint=os.environ.get('ENDPOINT_NAME', f'itcs355-{cfg.project_id}-predict'); payload={'temp_c':70.0,'vibration_mm_s':5.0,'pressure_kpa':100.0,'hours_since_service':1000.0,'load_pct':50.0,'ambient_humidity':50.0}; print(adapter.invoke(endpoint, payload))"

loadtest: ## Load test at multiple concurrency levels
	@for vus in 1 10 50; do \
		echo "=== $$vus VUs ==="; \
		k6 run -e TARGET=$(TARGET) -e VUS=$$vus loadtest/k6.js || true; \
	done

canary: ## Deploy canary revision and shift traffic 90/10
	SERVE_IMAGE_TAG=$(TAG) python scripts/canary_roll.py canary --version $(CANARY_VERSION)

rollback: ## Roll back traffic to the production revision
	python scripts/canary_roll.py rollback

# --- Lab 4 -------------------------------------------------------------------
inject-drift: ## Shift a feature's distribution on purpose
	python scripts/inject_drift.py --feature temp_c --mode shift --magnitude 6

drift: ## Score drift against the reference window
	python -m monitoring.drift --current data/current.csv

# --- Lab 5 -------------------------------------------------------------------
pipeline: ## Compile pipeline/pipeline.yaml for your provider
	python -c "from cloudlayer.pipelines import compile_for; from src import config; \
	compile_for(config.load().provider)"

llm-eval: ## Run the LLM golden set against recorded responses (offline, free)
	python scripts/llm_eval.py --out reports/llm_eval-baseline.json

llm-gate: ## Prove the gate fails on a degraded set — expected to exit non-zero
	python scripts/llm_eval.py --out reports/llm_eval-baseline.json >/dev/null
	python scripts/llm_eval.py --responses evals/fixtures/triage-regressed.jsonl \
	  --out reports/llm_eval.json --baseline reports/llm_eval-baseline.json

swap-check: ## Prove the portability seam against a second provider
	python scripts/portability_swap_check.py --second-provider $(SECOND)
