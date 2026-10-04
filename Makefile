# ClaimCheck — reproducible build targets.
#
# Everything runs offline in mock mode from a clean clone. Live registry probing
# is opt-in (make scan-live) and requires `requests`.

PY ?= python3
VENV ?= .venv
BIN := $(VENV)/bin
SAMPLES ?= samples
RESULTS ?= results
FIGURES ?= figures
SEEDS ?= 0 1 2

.PHONY: help setup data scan scan-live bench report figures all test clean reproduce

help:
	@echo "ClaimCheck make targets:"
	@echo "  make setup     - create venv and install (offline deps + package)"
	@echo "  make data      - (re)generate synthetic labeled orgs into $(SAMPLES)/"
	@echo "  make scan      - scan the bundled sample org (mock mode) -> console"
	@echo "  make scan-live - scan a repo against live PyPI/npm (TARGET=path; needs requests)"
	@echo "  make bench     - run the benchmark, write metrics + CSVs to $(RESULTS)/"
	@echo "  make report    - write sample reports (md/txt/sarif/json) to reports/"
	@echo "  make figures   - render all README charts into $(FIGURES)/"
	@echo "  make test      - run the test suite"
	@echo "  make all       - data + bench + figures + report + test"
	@echo "  make reproduce - clean regenerate of data, metrics, figures, reports"
	@echo "  make clean     - remove generated caches and build artifacts"

setup:
	$(PY) -m venv $(VENV)
	$(BIN)/python -m pip install --upgrade pip
	$(BIN)/python -m pip install -r requirements.txt
	$(BIN)/python -m pip install -e .
	@echo "setup complete. Activate with: source $(VENV)/bin/activate"

data:
	$(BIN)/python -m claimcheck.data.generate --out $(SAMPLES) --seeds $(SEEDS)

scan:
	$(BIN)/claimcheck scan $(SAMPLES)/acme \
		--oracle $(SAMPLES)/acme.oracle.json \
		--config $(SAMPLES)/acme.config.json

# Usage: make scan-live TARGET=/path/to/repo CONFIG=config/default.yml
TARGET ?= .
CONFIG ?= config/default.yml
scan-live:
	$(BIN)/claimcheck scan $(TARGET) --live --config $(CONFIG)

bench:
	$(BIN)/python experiments/benchmark.py --samples $(SAMPLES) --out $(RESULTS)

figures:
	$(BIN)/python experiments/make_figures.py --results $(RESULTS) --out $(FIGURES)

report:
	@mkdir -p reports
	$(BIN)/claimcheck scan $(SAMPLES)/acme --oracle $(SAMPLES)/acme.oracle.json \
		--config $(SAMPLES)/acme.config.json --format markdown -o reports/sample_exposure_report.md
	$(BIN)/claimcheck scan $(SAMPLES)/acme --oracle $(SAMPLES)/acme.oracle.json \
		--config $(SAMPLES)/acme.config.json --format table -o reports/sample_report.txt
	$(BIN)/claimcheck scan $(SAMPLES)/acme --oracle $(SAMPLES)/acme.oracle.json \
		--config $(SAMPLES)/acme.config.json --format sarif -o reports/sample.sarif
	$(BIN)/claimcheck scan $(SAMPLES)/acme --oracle $(SAMPLES)/acme.oracle.json \
		--config $(SAMPLES)/acme.config.json --format json -o reports/sample.json

test:
	$(BIN)/python -m pytest -q

all: data bench figures report test

reproduce: clean data bench figures report
	@echo "reproduced: samples/, results/, figures/, reports/"

clean:
	rm -rf .claimcheck_cache **/__pycache__ src/**/__pycache__ \
		.pytest_cache *.egg-info src/*.egg-info
	@echo "cleaned caches and build artifacts (generated samples/results/figures kept)"
