MATCHBOX ?= matchbox
PYTHON ?= python3

.PHONY: build build-plugin test check clean
build:
	MATCHBOX="$(MATCHBOX)" $(PYTHON) tools/build.py --output dist/hwatch

build-plugin:
	MATCHBOX="$(MATCHBOX)" $(PYTHON) tools/build.py --output plugin/bin/hwatch

test:
	MATCHBOX="$(MATCHBOX)" $(PYTHON) tests/acceptance.py
	$(PYTHON) tests/install.py
	MATCHBOX="$(MATCHBOX)" $(PYTHON) tests/plugin.py

check:
	MATCHBOX="$(MATCHBOX)" $(PYTHON) tests/source_free.py

clean:
	rm -rf dist plugin/bin
