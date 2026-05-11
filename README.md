# pip-rns

Install Python packages directly from [Reticulum](https://reticulum.network/) `rns://` git remotes via pip, pipx, uv, or poetry.

## Features

- **Multi-backend** — install with pip, pipx, uv, or poetry (`--pipx` / `--uv` / `--poetry`)
- **Version pinning** — `pipx-rns install repo@v1.0.0` or `--ref v1.0.0`
- **Offline cache** — `--use-cache` / `PIP_RNS_USE_CACHE=1` keeps a local copy for repeat or air-gapped installs
- **Editable mode** — `--editable` / `-e` for persistent checkouts
- **pipx inject** — `pipx-rns inject <venv> <remote>` installs into an existing pipx venv
- **Aliases** — short names for long remote paths
- **Indexes** — sync package listings from remote RNS repos (`packages`)

## Install and Usage

```bash
pip install pip-rns
pip-rns install 926baefe13daf5178c174f158dae1b45/quad4/LXMFy --break-system-packages
```

Install from wheel:

```bash
pip install pip_rns-*.whl
```

## Commands

### `pip-rns` (generic)

```
pip-rns install <identity/group/repo> [--pipx] [--uv] [--poetry] [--ref TAG] [--editable] [--use-cache] [--venv PATH] [-- <tool flags>]
pip-rns update <remote> [options]
pip-rns list [--pipx] [--uv] [--poetry]
pip-rns uninstall <package> [--pipx] [--uv] [--poetry]
pip-rns alias add|set|rm|ls
pip-rns index add|rm|ls|sync|packages
```

### `pipx-rns` (pipx-specific)

```
pipx-rns install <remote> [--ref TAG] [--editable]
pipx-rns inject <venv> <remote>
pipx-rns update <remote>
pipx-rns list
pipx-rns uninstall <package>
```

### Aliases

Save long remote paths under a short name and install by alias:

```bash
pip-rns alias add lxmfy 926baefe13daf5178c174f158dae1b45/quad4/LXMFy
pip-rns alias ls
pip-rns install lxmfy
```

Aliases are stored in `~/.config/pip-rns/aliases` (`%APPDATA%/pip-rns/aliases` on Windows), one per line:

```
lxmfy=926baefe13daf5178c174f158dae1b45/quad4/LXMFy
```

Use a custom config directory:
```bash
pip-rns --config /path/to/dir alias add lxmfy <remote>
PIP_RNS_CONFIG=/path/to/dir pip-rns install lxmfy
```

### Indexes

Register a remote index (an rngit repo with a `packages` file) and install by package name:

```bash
pip-rns index add rns://926baefe13daf5178c174f158dae1b45/quad4/index
pip-rns index sync
pip-rns index packages
pip-rns install lxmfy   # resolves from synced index
```

Indexes chain with aliases: local aliases take priority, then synced indexes, then raw path.

### Passthrough examples

```bash
# pass --break-system-packages to pip
pip-rns install identity/group/repo -- --break-system-packages

# pass --dev to poetry
pip-rns install --poetry identity/group/repo -- --dev

# pass --force to pipx
pipx-rns install identity/group/repo -- --force
```

## Environment

| Variable | Default | Description |
|---|---|---|
| `PIP_RNS_PIP` | `pip` | pip command |
| `PIP_RNS_PIPX` | `pipx` | pipx command |
| `PIP_RNS_UV` | `uv` | uv command |
| `PIP_RNS_POETRY` | `poetry` | poetry command |
| `PIP_RNS_CONFIG` | — | config directory for aliases |
| `PIP_RNS_USE_CACHE` | — | enable cache (`1`) |
| `PIP_RNS_COLOR` | `1` | disable colors (`0`) |
| `NO_COLOR` | — | disable colors (standard) |

## Tests

```bash
python -m tests.test_runner
python -m tests.test_runner -v       # verbose
python -m tests.test_runner -f retry # filter
```

## License

BSD 2-Clause. See [LICENSE](LICENSE).
