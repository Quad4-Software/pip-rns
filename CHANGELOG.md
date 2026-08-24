# Changelog

## 1.3.2

- `pip-rns browse` — listen, save, scan, and optionally install in one flow
- `pip-rns search` across aliases, indexes, and discovered packages
- Interactive `help` and empty `install` (package picker) on TTY
- Local `.whl` install from file or export directory
- `pip-rns doctor --fix` suggests fix commands
- Auto-alias prompt after browse/discover scan
- Install hints and defaults use short package names
- Trust prompt when remote is unpinned
- Branch installs hint when a release wheel exists

## 1.3.1

- Trust store for release publishers (`trust add|rm|ls|set-default`)
- `--offline`, `--insecure`, `--require-release`, and `--yes` install flags
- `pip-rns export` for sneakernet wheel mirrors
- `pip-rns discover` — listen, store, and scan announced RNS nodes
- Short-name install from discovered packages
- Signed releases fail closed unless verified or `--insecure`
- RNS source installs use a local cache instead of full reclones
- Bare remotes prompt for install mode on TTY
- Ctrl-C and prompt cancel exit cleanly

## 1.3.0

- Remembered install destinations and virtualenvs
- `doctor` and shell completion for pip-rns and opip
- Non-interactive mode for CI
- Auto-select release wheels when available
- Signature verification by default (`.rsg` sidecars and `.rsm`/`.rsg` via rngit)
- Safer zip/wheel extract and artifact path handling
- Clearer install failure recovery (PEP 668, permissions, venv prompts)
- Backend contract tests for pip, pipx, uv, and poetry

### Removed

- First-run prompt that offered a vendor package index

## 1.2.0

- opip offline wheel bundles (create, verify, install, export, update, uninstall)
- Integrity hashes, lock, and SBOM in bundles
- Reticulum identity signing and verify
- Install from local files, HTTP, FTP, git, or RNS remotes
- pip-rns bundle install and verify
- Shell completions and man pages for pip-rns, pipx-rns, and opip
