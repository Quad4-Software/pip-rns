# pip-rns

Install Python packages over [Reticulum](https://reticulum.network/) from rngit remotes. Supports pip, pipx, uv and poetry.

rngit: `5399f5a0212477618821e91e88ce053b:/page/index.mu`

## Features

- **Multi-backend** - install with pip, pipx, uv, or poetry
- **Version pinning** - `pipx-rns install repo@v1.0.0` or `--ref v1.0.0`
- **Releases** - install pre-built `.whl` files from rngit releases (`--from-release`)
- **Signature verification** - verify `.rsg` signatures before installing (`--verify <identity>`)
- **Offline cache** - `--use-cache` for repeat or offline installs
- **Editable mode** - `--editable` for persistent checkouts
- **pipx inject** - install into existing pipx venvs
- **Aliases** - short names for long remote paths
- **Indexes** - sync package listings from remote RNS repos

## Requirements

- rns `1.2.0` or higher
- python 3.7 or higher

## Install

**Install from local wheel:**

```bash
pip install pip_rns-*.whl
```

**From Source (rngit)**

```bash
git clone rns://926baefe13daf5178c174f158dae1b45/quad4/pip-rns
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
pip install git+https://git.quad4.io/RNS-Things/pip-rns
pip install git+https://github.com/Quad4-Software/pip-rns
```

## Verify Releases

```bash
rnid -i e46112d44649266d71fe2193e00a4710 -V pip_rns-*.rsg
```

## Usage

```bash
pipx-rns install 926baefe13daf5178c174f158dae1b45/quad4/LXMFy
# or 
pipx-rns install 926baefe13daf5178c174f158dae1b45/quad4/LXMFy@v1.6.3
```

### Adding Quad4 Index

```bash
pip-rns index add rns://926baefe13daf5178c174f158dae1b45/quad4/index
pip-rns index list
```

## Commands

### `pip-rns` (generic)

```
pip-rns install <identity/group/repo> [--pipx] [--uv] [--poetry] [--ref TAG] [--editable] [--use-cache] [--venv PATH] [--from-release] [--verify IDENTITY] [-- <tool flags>]
pip-rns update <remote> [options]
pip-rns list [--pipx] [--uv] [--poetry]
pip-rns uninstall <package> [--pipx] [--uv] [--poetry]
pip-rns alias add|set|rm|ls
pip-rns index add|rm|ls|sync|list|search
pip-rns release list|view
```

### `pipx-rns` (pipx-specific)

```
pipx-rns install <remote> [--ref TAG] [--editable] [--from-release] [--verify IDENTITY]
pipx-rns inject <venv> <remote>
pipx-rns update <remote>
pipx-rns list
pipx-rns uninstall <package>
```

### Releases

Install pre-built `.whl` from an rngit release (faster, no build step):

```bash
pip-rns install --from-release rns://926baefe13daf5178c174f158dae1b45/quad4/pip-rns --ref v1.0.0
```

Verify the artifact's `.rsg` signature before installing:

```bash
pip-rns install --from-release rns://id/group/repo --ref v1.0.0 --verify <identity>
```

List and view releases:

```bash
pip-rns release list rns://926baefe13daf5178c174f158dae1b45/quad4/pip-rns
pip-rns release view rns://926baefe13daf5178c174f158dae1b45/quad4/pip-rns v1.0.0
```

**Note:** The NomadNet page node is required for artifact downloads. If it differs from the rngit node, set `PIP_RNS_NOMADNET_NODE`.

### Aliases

Save long remote paths under a short name:

```bash
pip-rns alias add lxmfy 926baefe13daf5178c174f158dae1b45/quad4/LXMFy
pip-rns alias ls
pip-rns install lxmfy
```

Aliases are stored in `~/.config/pip-rns/aliases` (`%APPDATA%/pip-rns/aliases` on Windows):

```
lxmfy=926baefe13daf5178c174f158dae1b45/quad4/LXMFy
```

Custom config directory:

```bash
pip-rns --config /path/to/dir alias add lxmfy <remote>
PIP_RNS_CONFIG=/path/to/dir pip-rns install lxmfy
```

### Indexes

Register an index (an rngit repo with a `packages` file) and install by name:

```bash
pip-rns index add rns://identity/group/index
pip-rns index sync
pip-rns index list
pip-rns install lxmfy
```

Indexes chain with aliases: local aliases take priority, then synced indexes, then raw path.

### Passthrough

Flags after `--` are forwarded to the underlying tool:

```bash
pip-rns install identity/group/repo -- --break-system-packages
pip-rns install --poetry identity/group/repo -- --dev
pipx-rns install identity/group/repo -- --force
```

## Environment

| Variable | Default | Description |
|---|---|---|
| `PIP_RNS_PIP` | `pip` | pip command |
| `PIP_RNS_PIPX` | `pipx` | pipx command |
| `PIP_RNS_UV` | `uv` | uv command |
| `PIP_RNS_POETRY` | `poetry` | poetry command |
| `PIP_RNS_CONFIG` | - | config directory for aliases |
| `PIP_RNS_USE_CACHE` | - | enable cache (`1`) |
| `PIP_RNS_COLOR` | `1` | disable colors (`0`) |
| `PIP_RNS_NOMADNET_NODE` | - | page node hash for artifact downloads |
| `NO_COLOR` | - | disable colors (standard) |

## Shell Completions

```bash
# Bash
cp completions/pip-rns.bash ~/.local/share/bash-completion/completions/
# ZSH
cp completions/_pip-rns ~/.local/share/zsh/site-functions/
# Fish
cp completions/pip-rns.fish ~/.local/share/fish/vendor_completions.d/
```

## Man Pages

```bash
cp man/man1/pip-rns.1 ~/.local/share/man/man1/
cp man/man1/pipx-rns.1 ~/.local/share/man/man1/
```

## Tests

```bash
python -m tests.test_runner
python -m tests.test_runner -v
python -m tests.test_runner -f search

# Optional live tests (requires RNS, 60+ seconds):
PIP_RNS_NOMADNET_NODE=5399f5a0212477618821e91e88ce053b PIP_RNS_TEST_LIVE=1 python -m tests.test_runner -f live
```

## License

BSD 2-Clause. See [LICENSE](LICENSE).
