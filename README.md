# pip-rns

Install Python packages over [Reticulum](https://reticulum.network/) from remotes you choose, and share integrity-backed offline wheel bundles (`.opip`) for sneakernet / air-gap paths.

You pick every source. There is no default vendor index. Indexes and aliases are opt-in. PyPI, HTTPS git, and system pip remain available as bridges when you need them, not as the center of the design.

rngit page (optional peer docs): `132f67e79d9b24aad014e93015fb858f:/page/index.mu`

Read the [docs](docs/README.md)

## Tools

| Tool | Purpose |
|------|---------|
| `pip-rns` / `pipx-rns` | Install from Reticulum rngit remotes via pip, pipx, uv, or poetry |
| `opip` | Build, verify, and install offline `.opip` bundles for USB / air-gap |

Both ship in this package. `opip` uses only the Python standard library (no extra dependencies).

## Choose your sources

1. **Sneakernet first-class**: build or export a bundle, copy offline, verify, install.
2. **Release wheel over RNS**: prefer signed rngit releases (cheaper than a full source clone).
3. **Source clone**: expensive on RNS. Cached and updated when possible. Confirm before the first pull.
4. **Indexes** (optional): register peer package lists you trust. None are shipped pre-selected.

```bash
# Offline / USB
opip create -r requirements.txt -o ./pkg.opip
opip export ./pkg.opip -o /media/usb/pkg.opip
opip verify /media/usb/pkg.opip --require-signature
opip install /media/usb/pkg.opip

# Mirror a release wheel for sneakernet
pip-rns export rns://identity/group/repo --ref v1.0.0 -o /media/usb/mirror
pip-rns install /media/usb/mirror/pkg-1.0.0-py3-none-any.whl

# Online: browse mesh, install by short name
pip-rns browse --install
pip-rns install lxmfy
pip-rns search lxm

# Or step by step
pip-rns discover --seconds 60 --save --scan
pip-rns install lxmfy

# Pin or remember publisher
pip-rns trust add rns://identity/group/repo e46112d44649266d71fe2193e00a4710
pip-rns install --from-release rns://identity/group/repo --ref v1.0.0
pip-rns install --offline rns://identity/group/repo   # cache hit only
```

## pip-rns

### Features

- **Multi-backend** - install with pip, pipx, uv, or poetry
- **Version pinning** - `pipx-rns install repo@v1.0.0` or `--ref v1.0.0`
- **Releases** - install pre-built `.whl` files from rngit releases (`--from-release` / `--require-release`)
- **Trust store** - remember publisher identities (`pip-rns trust`). `--verify` for one-off pins
- **Fail closed** - signed releases must verify unless you pass `--insecure`
- **Offline** - `--offline` uses cache / local paths only (no RNS fetch)
- **Export** - `pip-rns export` mirrors release artifacts for USB sharing
- **Editable mode** - `--editable` for persistent checkouts
- **pipx inject** - install into existing pipx venvs
- **Aliases** - short names for long remote paths
- **Indexes** - opt-in sync of package listings from remotes you register
- **Discover** - listen for announced rngit nodes (`git.repositories`) on the mesh
- **Browse** - one command to listen, scan, alias, and install (`pip-rns browse`)
- **Search** - find packages across aliases, indexes, and discovery
- **Local wheels** - install exported `.whl` files from USB paths

### Requirements

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

**Bridge: PyPI** (optional HTTPS path)

```bash
pip install pip-rns
# or
pipx install pip-rns
```

**Bridge: git over HTTPS**

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
# branch (clones source. no release probe)
pip-rns install rns://7649a50d84610232d1416b41d2896aff/reticulum/reticulum@master
```

#### Adding an index (opt-in peer list)

```bash
pip-rns index add rns://identity/group/index
pip-rns index list
```

You choose which indexes to trust. None are added automatically.

### Commands

#### `pip-rns` (generic)

```
pip-rns [install] <identity/group/repo> [--from-release|--from-source|-s] [--require-release]
        [--offline] [--insecure] [--verify IDENTITY] [--yes|-y]
        [--pipx] [--uv] [--poetry] [--ref TAG] [--editable] [--use-cache]
        [--venv PATH] [--remember-venv] [-- <tool flags>]
pip-rns browse [--seconds N] [--install] [--auto-alias] [--no-listen] [--no-scan]
pip-rns search <query>
pip-rns help [COMMAND] [-i]
pip-rns update <remote> [options]
pip-rns export <remote> -o DIR [--ref TAG] [--verify IDENTITY] [--all]
pip-rns list [--pipx] [--uv] [--poetry]
pip-rns uninstall <package> [--pipx] [--uv] [--poetry]
pip-rns alias add|set|rm|ls
pip-rns trust add|rm|ls|set-default|forget-default
pip-rns discover [listen|ls|clear|scan|packages] [--seconds N] [--save] [--scan]
pip-rns index add|rm|ls|sync|list|search
pip-rns release list|view
pip-rns venv list|set|forget
pip-rns bundle install|verify
pip-rns doctor [--fix] [--online --remote RNS_URL]
pip-rns completion install [--shell bash|zsh|fish]
```

`pip-rns rns://id/group/repo` is shorthand for install. With no `@ref` / mode flags on a TTY, you get a menu (latest release preferred, source clone labeled expensive, pick a release). Install prefers a release `.whl` when one exists (use `--from-source`/`-s` to force a clone, or `--from-release` / `--require-release` to require a wheel). Branch-like refs such as `@master` or `@main` clone from source automatically. RNS source installs reuse `~/.local/share/pip-rns/cache` and fetch/update on repeat (set `PIP_RNS_NO_CACHE=1` to force a fresh temp clone). `--offline` never contacts RNS. Indexes are opt-in: add only remotes you choose.

#### `pipx-rns` (pipx-specific)

```
pipx-rns install <remote> [--ref TAG] [--editable] [--from-release|--from-source]
         [--require-release] [--offline] [--insecure] [--verify IDENTITY] [--yes]
pipx-rns inject <venv> <remote>
pipx-rns update <remote>
pipx-rns list
pipx-rns uninstall <package>
pipx-rns doctor [--online]
pipx-rns completion install
```

#### Releases

Install pre-built `.whl` from an rngit release (faster, no build step):

```bash
pip-rns install --from-release rns://06a54b505bb67b25ef3f8097e8001edc/public/rns-page-node --ref v1.6.0
```

Require a specific release signer when installing (or save it with `pip-rns trust`):

```bash
pip-rns install --from-release rns://id/group/repo --ref v1.0.0 --verify e46112d44649266d71fe2193e00a4710
pip-rns trust add rns://id/group/repo e46112d44649266d71fe2193e00a4710
```

List, view, and export releases:

```bash
pip-rns release list rns://06a54b505bb67b25ef3f8097e8001edc/public/rns-page-node
pip-rns release view rns://06a54b505bb67b25ef3f8097e8001edc/public/rns-page-node v1.6.0
pip-rns export rns://06a54b505bb67b25ef3f8097e8001edc/public/rns-page-node --ref v1.6.0 -o ./mirror
```

Release artifacts are downloaded via `rngit release fetch` on the rngit node hosting the repository. Signed releases fail closed if verification is not confirmed unless you pass `--insecure`.

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

#### Trust

```bash
pip-rns trust add rns://id/group/repo e46112d44649266d71fe2193e00a4710
pip-rns trust set-default e46112d44649266d71fe2193e00a4710
pip-rns trust ls
```

Stored in `~/.config/pip-rns/trust.json`. Used automatically when `--verify` is omitted (unless `--insecure`).

#### Discover

rngit nodes announce on the `git.repositories` aspect. Listen on your local Reticulum stack (requires the `rns` Python package):

```bash
pip-rns discover --seconds 60 --save
pip-rns discover ls
```

Heard destination hashes can be used as `rns://<destination_hash>/group/repo` when the path is known. Discovery is passive. You only learn nodes that announce during the listen window.

Scan those nodes for Python packages (Nomad catalog when enabled, common `packages` index repos, and release `.whl` checks):

```bash
pip-rns discover --save --scan
# or later:
pip-rns discover scan
pip-rns discover packages
pip-rns install lxmfy
```

Short names from discovery resolve after aliases and registered indexes.

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
| `PIP_RNS_COLOR` | `auto` | `auto`, `always`, `never` (or `0`/`1`) |
| `PIP_RNS_NO_INTERACTIVE` | - | disable prompts when set |
| `NO_COLOR` | - | disable colors (standard) |
| `FORCE_COLOR` | - | force colors (standard) |
| `CI` | - | disables prompts and color unless `FORCE_COLOR` |

Color stays off on classic Windows `cmd.exe` / PowerShell unless Windows Terminal (`WT_SESSION`), ConEmu/ANSICON, or `FORCE_COLOR` is set. Global flag: `--no-interactive`. Long RNS waits show a TTY spinner (`Waiting on Reticulum…`).

Remember a venv: `pip-rns install … --venv /path --remember-venv` or `pip-rns venv set default /path`.

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

Signed bundles (Reticulum RSG). A present `.rsg` is verified automatically via the embedded pubkey. Pass `--signer` to pin a required identity:

```bash
opip keygen -o publisher.rns
opip create -r requirements.txt --publisher "My Team" --identity publisher.rns --require-pypi-hash
opip verify shared-bundle.opip
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
| `install SOURCE [--target DIR] [--remember-target] [--signer IDENTITY]` | Install a bundle |
| `dest list\|set\|forget` | Remembered install destinations per bundle |
| `uninstall BUNDLE [--user]` | Uninstall by registered bundle name |
| `update BUNDLE [-o FILE]` | Rebuild a registered bundle |
| `export SOURCE -o FILE` | Copy a verified bundle for sharing |
| `verify BUNDLE [--signer IDENTITY] [--require-signature]` | Verify integrity and authenticity |
| `keygen -o FILE` | Generate Reticulum identity for signing |
| `info BUNDLE` | Show bundle metadata |
| `list [bundles\|installed]` | List registry |
| `doctor` | Check environment health |
| `completion install` | Install shell completions |
| `help [COMMAND] [-i]` | Interactive or per-command help |
| `register-windows` | Register `.opip` association and context menus |

Global flags: `--no-color`, `--no-interactive` / `-y`, `--data-dir`, `--version`.

Remember a per-bundle install destination after `opip install --target DIR` (prompted when interactive), or use `--remember-target` / `opip dest set NAME PATH`. Later installs reuse that path when `--target` is omitted.

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
| `OPIP_NO_COLOR` | Disable color when set |
| `OPIP_FORCE_COLOR` | Force color when set |
| `OPIP_NO_INTERACTIVE` | Disable prompts when set |
| `NO_COLOR` | Standard. Disables colors when set |
| `FORCE_COLOR` | Standard. Enables colors when set |
| `CI` | disables prompts and color unless `FORCE_COLOR` |
| `PIP_RNS_CONFIG` | pip-rns config directory. aliases are resolved for `rns://` installs |

## Shell Completions

```bash
pip-rns completion install
opip completion install
# or pick a shell explicitly:
pip-rns completion install --shell zsh
```

Manual copy (same destinations):

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
