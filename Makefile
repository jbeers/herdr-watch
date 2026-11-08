MATCHBOX ?= matchbox
PYTHON ?= python3

.PHONY: build test check clean
build:
	MATCHBOX="$(MATCHBOX)" $(PYTHON) tools/build.py --output dist/hwatch

test:
	MATCHBOX="$(MATCHBOX)" $(PYTHON) tests/acceptance.py
	$(PYTHON) tests/install.py

check:
	MATCHBOX="$(MATCHBOX)" $(PYTHON) tests/source_free.py

clean:
	rm -rf dist
