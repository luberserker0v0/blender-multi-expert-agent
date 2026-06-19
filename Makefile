PYTHON ?= python

.PHONY: install test run run-stream run-dev

install:
	$(PYTHON) -m pip install --upgrade pip
	$(PYTHON) -m pip install -r requirements.txt

test:
	$(PYTHON) scripts/run_all_tests.py

run:
	$(PYTHON) scripts/run_pipeline.py --task "build an apple"

run-stream:
	$(PYTHON) scripts/run_pipeline.py --task "build an apple"

run-dev:
	$(PYTHON) scripts/run_dev.py
