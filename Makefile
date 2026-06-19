PYTHON ?= python

.PHONY: install test docs-check ci cd run run-stream run-dev

install:
	$(PYTHON) -m pip install --upgrade pip
	$(PYTHON) -m pip install -r requirements.txt

test:
	PYTHONPATH=src $(PYTHON) -m pytest tests/unit -q

docs-check:
	$(PYTHON) scripts/check_docs.py

ci:
	$(PYTHON) scripts/run_local_ci.py

cd:
	$(PYTHON) scripts/run_local_cd.py

run:
	$(PYTHON) scripts/run_pipeline.py --task "build an apple"

run-stream:
	$(PYTHON) scripts/run_pipeline.py --task "build an apple"

run-dev:
	$(PYTHON) scripts/run_dev.py
