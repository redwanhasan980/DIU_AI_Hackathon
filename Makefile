.PHONY: setup setup-py setup-web data sample train evaluate simulate plots narratives all api web demo test e2e lint clean-artifacts

VENV   := .venv
PY     := $(abspath $(VENV))/bin/python
BACK   := backend
FRONT  := frontend

setup: setup-py setup-web

setup-py:
	@if command -v uv >/dev/null 2>&1; then uv venv $(VENV) -q && uv pip install -q --python $(PY) -e "$(BACK)[dev]"; \
	else python3 -m venv $(VENV) && $(PY) -m pip install -q -e "$(BACK)[dev]"; fi

setup-web:
	cd $(FRONT) && npm ci

data:            ## generate the full synthetic dataset -> data/generated/
	cd $(BACK) && $(PY) -m floatwise.data.generate

sample:          ## rebuild the small committed sample -> data/sample/
	cd $(BACK) && $(PY) -m floatwise.data.generate --sample

train:           ## train LightGBM quantile models -> artifacts/models/
	cd $(BACK) && $(PY) -m floatwise.models.train

evaluate:        ## metrics + forecasts + model card -> artifacts/
	cd $(BACK) && $(PY) -m floatwise.models.evaluate

simulate:        ## backtest status quo vs FloatWise -> artifacts/simulation_default.json
	cd $(BACK) && $(PY) -m floatwise.simulation.backtest

plots:           ## synthetic-data check charts -> artifacts/plots/
	cd $(BACK) && $(PY) scripts/plot_data_checks.py

narratives:      ## pre-generate bn/en explanations -> artifacts/narratives_cache.json
	cd $(BACK) && $(PY) scripts/build_narratives.py

all: data train evaluate simulate plots narratives

api:
	cd $(BACK) && $(PY) -m uvicorn floatwise.api.main:app --reload --port 8000

web:
	cd $(FRONT) && npm run dev

demo:            ## API + web from cached artifacts (works offline)
	@test -f artifacts/forecasts.parquet || (echo "artifacts missing -> running 'make all' first" && $(MAKE) all)
	cd $(FRONT) && npm run build
	cd $(BACK) && FLOATWISE_SERVE_WEB=1 $(PY) -m uvicorn floatwise.api.main:app --port 8000

test:
	cd $(BACK) && $(PY) -m pytest

e2e:             ## browser walk-through of the SRS §14 demo (needs `make demo` running + playwright)
	cd $(BACK) && $(PY) scripts/e2e_demo.py $(if $(CHROME),--chrome $(CHROME),)

lint:
	cd $(BACK) && $(PY) -m ruff check . && $(PY) -m ruff format --check .
	@if [ -d $(FRONT)/node_modules ]; then cd $(FRONT) && npx tsc --noEmit && npm run lint; fi

clean-artifacts:
	rm -rf artifacts/models artifacts/*.parquet
