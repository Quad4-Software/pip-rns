# Changelog

## 1.5.0 - 2026-09-05

- Signed zipapps: opip.pyz and pip-rns.pyz (run without prior pip install)
- self-install places opip/pip-rns on PATH via manual extract, uv, or ensurepip
- opip kit create|verify builds USB/airgap kits with optional portable CPython
- get-opip.py bootstraps zipapps from a browser-downloaded wheel or Tor URL (no pip)
- opip kit create --as-app writes AppImage-style ./Run launchers
- SOCKS5(h)/HTTP proxy support for create and kit downloads (--proxy, OPIP_PROXY)
- Explicit --break-system-packages and --backend manual for no-pip installs
- pip-rns local wheel install falls back to uv/manual when pip is missing
- Doctor and help: opip help airgap, pip-rns help bootstrap

## 1.4.0 - 2026-09-04 [released]

- Browse can listen, save, scan, and optionally install in one flow
- Search across aliases, indexes, and discovered packages
- Interactive help and package picker when you run install with no arguments
- Install local wheels from a file or export directory
- Doctor --fix suggests commands to repair your setup
- Auto-alias prompt after browse or discover scan
- Install hints and defaults use short package names
- Trust prompt when a remote is unpinned
- Branch installs hint when a release wheel already exists
- opip prefers stable PyPI releases over prereleases (PEP 440 compare)
- opip install prompts to recover from PEP 668 (venv, --user, or --target)
- opip --user retries with --break-system-packages on Arch-style PEP 668
- opip refuses or recreates a venv when its Python version mismatches the bundle
- opip filters incompatible wheels and rejects unreadable venv interpreters
- CI test matrix covers Ubuntu, Windows, and macOS
- opip update reinstalls with replace (no uninstall-first), restores dest/venv, and can re-sign
- opip create from private indexes, local find-links, or offline wheel dirs
- opip create from uv.lock, poetry.lock, or pip-tools hashed locks
- opip SBOM is CycloneDX 1.5
- opip extract to a wheelhouse or PEP 503 simple index
- opip install with pip or uv backend
- opip json and quiet output for CI
- opip trust uses the shared pip-rns trust store
- opip update reuses unchanged wheels
- opip delta and apply for thin update packs

## 1.3.1 - 2026-07-23 [released]

- Trust store for release publishers (add, remove, list, set default)
- Offline, insecure, require-release, and yes flags for install
- Export for sneakernet wheel mirrors
- Discover listens, stores, and scans announced RNS nodes
- Install by short name from discovered packages
- Signed releases fail closed unless verified or insecure mode is on
- RNS source installs use a local cache instead of full reclones
- Bare remotes ask for install mode when run in a terminal
- Ctrl-C and prompt cancel exit cleanly

## 1.3.0 - 2026-07-23 [released]

- Remembered install destinations and virtualenvs
- Doctor and shell completion for pip-rns and opip
- Non-interactive mode for CI
- Auto-select release wheels when available
- Signature verification by default (rsg sidecars and rsm/rsg via rngit)
- Safer zip/wheel extract and artifact path handling
- Clearer install failure recovery (PEP 668, permissions, venv prompts)
- Backend contract tests for pip, pipx, uv, and poetry

### Removed

- First-run prompt that offered a vendor package index

## 1.2.0 - 2026-06-14 [released]

- opip offline wheel bundles (create, verify, install, export, update, uninstall)
- Integrity hashes, lock, and SBOM in bundles
- Reticulum identity signing and verify
- Install from local files, HTTP, FTP, git, or RNS remotes
- pip-rns bundle install and verify
- Shell completions and man pages for pip-rns, pipx-rns, and opip
