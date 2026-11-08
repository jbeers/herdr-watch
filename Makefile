MATCHBOX ?= matchbox
PYTHON ?= python3

.PHONY: build test check clean
build:
	mkdir -p dist
	$(MATCHBOX) --target native --output dist/hwatch src/main.bxs

test:
	MATCHBOX="$(MATCHBOX)" $(PYTHON) tests/acceptance.py
	$(PYTHON) tests/install.py

check:
	MATCHBOX="$(MATCHBOX)" $(PYTHON) tests/source_free.py

clean:
	rm -rf dist
