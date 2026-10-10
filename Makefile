PYTHON ?= python3
ARGS ?= --help

.PHONY: explore corpus test-explorer serve test-go differential seeds help

# Ejemplos y formato JSONL: tools/explorer/README.md
explore:
	$(PYTHON) tools/explorer/bb.py $(ARGS)

corpus:
	$(PYTHON) tools/explorer/corpus.py $(ARGS)

test-explorer:
	$(PYTHON) -m unittest discover -s tools/explorer -p 'test_*.py'

# Reemplazo Go. Lista explícita de claves runtime: nunca cargar BB_TOKEN.
serve:
	TEAM_TOKEN="$${TEAM_TOKEN:-$$(sed -n 's/^TEAM_TOKEN=//p' .env)}" \
	BEHAVIOR_VERSION="$${BEHAVIOR_VERSION:-$$(sed -n 's/^BEHAVIOR_VERSION=//p' .env)}" \
	STORAGE="$${STORAGE:-$$(sed -n 's/^STORAGE=//p' .env)}" \
	STATE_PATH="$${STATE_PATH:-$$(sed -n 's/^STATE_PATH=//p' .env)}" \
	go run ./cmd/replacement

test-go:
	go vet ./... && go test ./...
	$(PYTHON) -m unittest discover -s tools/capture -p 'test_*.py'

# Arnés diferencial: reemplazo contra la evidencia grabada (tests/differential/README.md).
differential:
	BEHAVIOR_VERSION="$(BEHAVIOR_VERSION)" go test ./tests/differential -run TestCorpus -v

# Capturas (archivo o volcado de logs) -> semillas por secuencia: tools/capture/seeds.py
seeds:
	$(PYTHON) tools/capture/seeds.py $(ARGS)

help:
	@echo 'make explore ARGS="budget"'
	@echo 'make explore ARGS="run SEQ tmp/sondas.jsonl --no-cache"'
	@echo 'make corpus ARGS="build" (snapshot offline)'
	@echo 'make corpus ARGS="replay --epoch v1 --prefix a2-v1-YYYYMMDD" (224 requests)'
	@echo 'make test-explorer (servidor simulado; sin requests al original)'
	@echo 'make serve (reemplazo en :9900, captura en var/capture.jsonl)'
	@echo 'make test-go'
	@echo 'make differential [BEHAVIOR_VERSION=v1|v2] (v2 por defecto)'
	@echo 'make seeds ARGS="var/capture.jsonl railway.log -o tests/seeds/eval.jsonl"'
