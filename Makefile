PYTHON ?= python3
ARGS ?= --help

.PHONY: explore test-explorer help

# Ejemplos y formato JSONL: tools/explorer/README.md
explore:
	$(PYTHON) tools/explorer/bb.py $(ARGS)

test-explorer:
	$(PYTHON) -m unittest tools/explorer/test_bb.py

help:
	@echo 'make explore ARGS="budget"'
	@echo 'make explore ARGS="run SEQ tmp/sondas.jsonl --no-cache"'
	@echo 'make test-explorer (servidor simulado; sin requests al original)'
