# pip-rns

Install Python packages over [Reticulum](https://reticulum.network/) from rngit remotes, and create or install integrity-backed offline wheel bundles (`.opip`).

rngit: `132f67e79d9b24aad014e93015fb858f:/page/index.mu`

## Tools

| Tool | Purpose |
|------|---------|
| `pip-rns` / `pipx-rns` | Install packages from Reticulum rngit remotes via pip, pipx, uv, or poetry |
| `opip` | Build, verify, and install offline wheel bundles for sneakernet / air-gap targets |

Both ship in this package. `opip` uses only the Python standard library (no extra dependencies).

## pip-rns

### Features

- **Multi-backend** - install with pip, pipx, uv, or poetry
- **Version pinning** - `pipx-rns install repo@v1.0.0` or `--ref v1.0.0`
- **Releases** - install pre-built `.whl` files from rngit releases (`--from-release`)
- **Signature verification** - require rngit release signatures (`--verify <identity>`)
- **Offline cache** - `--use-cache` for repeat or offline installs
- **Editable mode** - `--editable` for persistent checkouts
- **pipx inject** - install into existing pipx venvs
- **Aliases** - short names for long remote paths
- **Indexes** - sync package listings from remote RNS repos

### Requirements

- rns `1.2.0` or higher
- python 3.7 or higher

### Install

**Install from local wheel:**

```bash
pip install pip_rns-*.whl
```

**From Source (rngit)**

```bash
git clone rns://06a54b505bb67b25ef3f8097e8001edc/public/pip-rns
cd pip-rns
make
make install
```

**PyPI:**

```bash
pip install pip-rns
# or
pipx install pip-rns
```

**Install from git:**

```bash
pip install git+https://github.com/Quad4-Software/pip-rns
```

### Verify Releases

```bash
rnid -i e46112d44649266d71fe2193e00a4710 -V pip_rns-*.rsg
```

### Usage

```bash
pipx-rns install 06a54b505bb67b25ef3f8097e8001edc/public/LXMFy
# or 
pipx-rns install 06a54b505bb67b25ef3f8097e8001edc/public/LXMFy@v1.6.3
```

#### Adding Quad4 Index

```bash
pip-rns index add rns://06a54b505bb67b25ef3f8097e8001edc/public/index
pip-rns index list
```

### Commands

#### `pip-rns` (generic)

```
pip-rns install <identity/group/repo> [--pipx] [--uv] [--poetry] [--ref TAG] [--editable] [--use-cache] [--venv PATH] [--from-release] [--verify IDENTITY] [-- <tool flags>]
pip-rns update <remote> [options]
pip-rns list [--pipx] [--uv] [--poetry]
pip-rns uninstall <package> [--pipx] [--uv] [--poetry]
pip-rns alias add|set|rm|ls
pip-rns index add|rm|ls|sync|list|search
pip-rns release list|view
pip-rns bundle install|verify
```

#### `pipx-rns` (pipx-specific)

```
pipx-rns install <remote> [--ref TAG] [--editable] [--from-release] [--verify IDENTITY]
pipx-rns inject <venv> <remote>
pipx-rns update <remote>
pipx-rns list
pipx-rns uninstall <package>
```

#### Releases

Install pre-built `.whl` from an rngit release (faster, no build step):

```bash
pip-rns install --from-release rns://06a54b505bb67b25ef3f8097e8001edc/public/rns-page-node --ref v1.6.0
```

Require the release manifest signer when installing:

```bash
pip-rns install --from-release rns://id/group/repo --ref v1.0.0 --verify e46112d44649266d71fe2193e00a4710
```

List and view releases:

```bash
pip-rns release list rns://06a54b505bb67b25ef3f8097e8001edc/public/rns-page-node
pip-rns release view rns://06a54b505bb67b25ef3f8097e8001edc/public/rns-page-node v1.6.0
```

Release artifacts are downloaded via `rngit release fetch` on the rngit node hosting the repository.

#### Aliases

Save long remote paths under a short name:

```bash
pip-rns alias add lxmfy 06a54b505bb67b25ef3f8097e8001edc/public/LXMFy
pip-rns alias ls
pip-rns install lxmfy
```

Aliases are stored in `~/.config/pip-rns/aliases` (`%APPDATA%/pip-rns/aliases` on Windows):

```
lxmfy=06a54b505bb67b25ef3f8097e8001edc/public/LXMFy
```

Custom config directory:

```bash
pip-rns --config /path/to/dir alias add lxmfy <remote>
PIP_RNS_CONFIG=/path/to/dir pip-rns install lxmfy
```

#### Indexes

Register an index (an rngit repo with a `packages` file) and install by name:

```bash
pip-rns index add rns://identity/group/index
pip-rns index sync
pip-rns index list
pip-rns install lxmfy
```

Indexes chain with aliases: local aliases take priority, then synced indexes, then raw path.

#### Bundles (opip integration)

Install or verify offline `.opip` bundles using pip-rns aliases and config:

```bash
pip-rns bundle install lxmfy-bundle@v1.0.0 --signer e46112d44649266d71fe2193e00a4710
pip-rns bundle verify ./my-bundle.opip --require-signature
```

#### Passthrough

Flags after `--` are forwarded to the underlying tool:

```bash
pip-rns install identity/group/repo -- --break-system-packages
pip-rns install --poetry identity/group/repo -- --dev
pipx-rns install identity/group/repo -- --force
```

### pip-rns Environment

| Variable | Default | Description |
|---|---|---|
| `PIP_RNS_PIP` | `pip` | pip command |
| `PIP_RNS_PIPX` | `pipx` | pipx command |
| `PIP_RNS_UV` | `uv` | uv command |
| `PIP_RNS_POETRY` | `poetry` | poetry command |
| `PIP_RNS_CONFIG` | - | config directory for aliases |
| `PIP_RNS_USE_CACHE` | - | enable cache (`1`) |
| `PIP_RNS_COLOR` | `1` | disable colors (`0`) |
| `NO_COLOR` | - | disable colors (standard) |

## opip (offline bundles)

Create and install integrity-backed offline Python wheel bundles (`.opip`).

### Features

- **create**: Fetch wheels from PyPI and pack them into an integrity-backed bundle
- **auto-detect**: Read `pyproject.toml`, `setup.py`, or `requirements.txt` from a cloned project
- **universal bundles**: `--platform universal` bundles wheels for Windows, Linux, and macOS in one file
- **install**: Install from a local bundle, HTTP/HTTPS/FTP/git, or Reticulum (`rns://`) source
- **export**: Copy a verified bundle for sneakernet / USB sharing
- **uninstall / update**: Manage registered bundles
- **verify**: Check integrity, authenticity, and PyPI provenance
- **Windows integration**: File association and Explorer context menus (`register-windows`)

Each bundle contains `manifest.json`, `integrity.json`, `lock.json`, `sbom.json`, optional `publisher.json`, plus a `wheels/` directory and pinned `requirements.txt`. Signed bundles also have a Reticulum `.rsg` sidecar (and optionally an `.rsm` release manifest when published via `rngit release`).

### Quick start

Bundle a cloned project on a connected machine:

```bash
git clone https://github.com/example/some-project.git
cd some-project
opip create
```

Copy the `.opip` file to the air-gapped machine:

```bash
opip verify my-bundle.opip
opip install my-bundle.opip
```

Install from an rngit release over Reticulum:

```bash
opip install rns://identity/group/repo@v1.0.0
opip install rns://identity/group/repo@v1.0.0:my-bundle.opip
```

Manual requirements and platform targeting:

```bash
opip create -o my-bundle.opip -r requirements.txt
opip create -r requirements.txt --python 3.12 --platform win_amd64
opip create -r requirements.txt --python 3.12 --platform universal
```

Signed bundles (Reticulum RSG):

```bash
opip keygen -o publisher.rns
opip create -r requirements.txt --publisher "My Team" --identity publisher.rns --require-pypi-hash
opip verify shared-bundle.opip --signer e46112d44649266d71fe2193e00a4710 --require-signature
```

Publish a signed bundle as an rngit release (creates `.rsm` manifest automatically):

```bash
rngit release -i publisher.rns rns://identity/group/repo create v1.0.0:./dist
```

### opip Commands

| Command | Description |
|---------|-------------|
| `create [-o FILE] [-C DIR] [-r REQ.txt] [packages...]` | Build a bundle |
| `install SOURCE [--signer IDENTITY] [--require-signature]` | Install a bundle |
| `uninstall BUNDLE [--user]` | Uninstall by registered bundle name |
| `update BUNDLE [-o FILE]` | Rebuild a registered bundle |
| `export SOURCE -o FILE` | Copy a verified bundle for sharing |
| `verify BUNDLE [--signer IDENTITY] [--require-signature]` | Verify integrity and authenticity |
| `keygen -o FILE` | Generate Reticulum identity for signing |
| `info BUNDLE` | Show bundle metadata |
| `list [bundles\|installed]` | List registry |
| `help [COMMAND] [-i]` | Interactive or per-command help |
| `register-windows` | Register `.opip` association and context menus |

### opip Environment

| Variable | Purpose |
|----------|---------|
| `OPIP_DATA_DIR` | State directory (same as `--data-dir`) |
| `OPIP_JOBS` | Default parallel downloads for `create` |
| `OPIP_PYTHON` | Default `--python` for `create` |
| `OPIP_PLATFORM` | Default `--platform` for `create` |
| `OPIP_PUBLISHER` | Default `--publisher` for `create` |
| `OPIP_IDENTITY` | Default `--identity` path for `create` |
| `OPIP_SIGNER` | Default `--signer` for `verify` and `install` |
| `OPIP_COLOR` | `auto`, `always`, or `never` |
| `NO_COLOR` | Standard; disables colors when set |
| `PIP_RNS_CONFIG` | pip-rns config directory; aliases are resolved for `rns://` installs |

## Shell Completions

```bash
# Bash
cp completions/pip-rns.bash ~/.local/share/bash-completion/completions/
cp completions/opip.bash ~/.local/share/bash-completion/completions/
# ZSH
cp completions/_pip-rns ~/.local/share/zsh/site-functions/
cp completions/_opip ~/.local/share/zsh/site-functions/
# Fish
cp completions/pip-rns.fish ~/.local/share/fish/vendor_completions.d/
cp completions/opip.fish ~/.local/share/fish/vendor_completions.d/
```

## Man Pages

```bash
cp man/man1/pip-rns.1 ~/.local/share/man/man1/
cp man/man1/pipx-rns.1 ~/.local/share/man/man1/
cp man/man1/opip.1 ~/.local/share/man/man1/
```

## Tests

```bash
python -m tests.test_runner
python -m tests.test_runner -v
python -m tests.test_runner -f opip

# Optional live tests (requires RNS, 60+ seconds):
PIP_RNS_TEST_LIVE=1 python -m tests.test_runner -f live
```

The test runner adds `src/` to `PYTHONPATH` automatically. Optional live tests are skipped unless `PIP_RNS_TEST_LIVE=1` is set.

## License

BSD 2-Clause. See [LICENSE](LICENSE).
