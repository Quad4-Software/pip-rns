EDITOR ?= nano
RNID_ID ?= e46112d44649266d71fe2193e00a4710
RNID_KEY ?= $(HOME)/.rngit/client_identity
RNS_REMOTE ?= rns://06a54b505bb67b25ef3f8097e8001edc/public/pip-rns
VERSION := $(shell sed -n 's/^__version__ = "\(.*\)"/\1/p' src/pip_rns/version.py)
TAG ?= v$(VERSION)
PREFIX ?= /usr/local

.PHONY: all clean build sign upload release release-rns tag retag test typecheck install install-user

all: build

clean:
	rm -rf dist/ build/ *.egg-info

build:
	python -m build --wheel --sdist

sign: build
	for f in dist/*.tar.gz dist/*.whl; do \
		rnid -f -i $(RNID_KEY) -s "$$f" -w "$$f.rsg"; \
	done

upload: sign
	twine upload dist/*.whl dist/*.tar.gz

release: tag release-rns

release-rns: sign
	mkdir -p dist
	RELEASE_TAG=$(TAG) EDITOR="$(PWD)/scripts/release-notes.sh" \
		rngit release -i $(RNID_KEY) $(RNS_REMOTE) create $(TAG):./dist

tag:
	@if git rev-parse -q --verify "refs/tags/$(TAG)" >/dev/null 2>&1; then \
		echo "Tag $(TAG) already exists. Use: make retag TAG=$(TAG)"; \
		echo "Or republish rngit only: make release-rns TAG=$(TAG)"; \
		exit 1; \
	fi
	git tag -s $(TAG) -m "$(TAG)"
	git push origin $(TAG)

retag:
	git tag -d $(TAG) 2>/dev/null || true
	-git push origin :refs/tags/$(TAG) 2>/dev/null || true
	git tag -s $(TAG) -m "$(TAG)"
	git push origin $(TAG)

test:
	python -m tests.test_runner

typecheck:
	uv run mypy

install:
	pip install --break-system-packages .
	mkdir -p ~/.local/share/man/man1
	cp man/man1/pip-rns.1 ~/.local/share/man/man1/
	cp man/man1/pipx-rns.1 ~/.local/share/man/man1/
	cp man/man1/opip.1 ~/.local/share/man/man1/
	mkdir -p ~/.local/share/bash-completion/completions
	cp completions/pip-rns.bash ~/.local/share/bash-completion/completions/
	cp completions/opip.bash ~/.local/share/bash-completion/completions/
	mkdir -p ~/.local/share/zsh/site-functions
	cp completions/_pip-rns ~/.local/share/zsh/site-functions/
	cp completions/_opip ~/.local/share/zsh/site-functions/
	mkdir -p ~/.local/share/fish/vendor_completions.d
	cp completions/pip-rns.fish ~/.local/share/fish/vendor_completions.d/
	cp completions/opip.fish ~/.local/share/fish/vendor_completions.d/