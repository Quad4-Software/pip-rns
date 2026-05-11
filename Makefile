EDITOR ?= nano
RNID_ID ?= e46112d44649266d71fe2193e00a4710
RNID_KEY ?= $(HOME)/.rngit/client_identity
RNS_REMOTE ?= rns://926baefe13daf5178c174f158dae1b45/quad4/pip-rns
TAG ?= v0.1.0

.PHONY: all clean build sign upload release tag test

all: build

clean:
	rm -rf dist/ build/ *.egg-info

build:
	python -m build --wheel --sdist

sign: build
	for f in dist/*.tar.gz dist/*.whl; do \
		rnid -i $(RNID_KEY) -s "$$f" -w "$$f.rsg"; \
	done

upload: sign
	twine upload dist/*

release: tag sign
	mkdir -p dist
	EDITOR="$(PWD)/scripts/release-notes.sh" \
		rngit release -i $(RNID_KEY) $(RNS_REMOTE) create $(TAG):./dist

tag:
	git tag -s $(TAG) -m "$(TAG)"
	git push origin $(TAG)

test:
	python -m tests.test_runner
