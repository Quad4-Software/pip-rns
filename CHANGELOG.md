# Changelog

## 1.5.1 - 2026-09-05

- Fix pip-rns install swallowing the remote as rns://install when using
  pip-rns install rns://... (install-command inject used the wrong argv index)

## 1.5.0 - 2026-09-05 [released]

### Zipapps, kits, and no-pip bootstrap

- Signed zipapps (opip.pyz, pip-rns.pyz) run with only a Python interpreter
- self-install places opip and pip-rns on PATH via manual extract, uv, or ensurepip
- get-opip.py builds those zipapps from a browser-downloaded wheel or Tor URL
- opip kit create / kit verify builds USB airgap kits with optional portable CPython
- kit create --as-app writes AppImage-style ./Run launchers
- HTTP(S) and SOCKS5(h) proxy for create and kit downloads (--proxy, OPIP_PROXY)
- --break-system-packages and --backend manual for installs when pip is absent
- pip-rns local wheel install falls back to uv or manual extract when pip is missing
- Help topics: opip help airgap, pip-rns help bootstrap

### Docs and repository hardening

- Docsify docs site on GitHub Pages (pip-rns.quad4.io)
- GitHub Actions supply-chain hardening (Harden Runner first, pinned workflows)
- Scorecard and CodeQL fixes (TLS 1.2 floor, safer URL handling, dependency policy)

## 1.4.0 - 2026-09-04 [released]

### pip-rns

- Browse can listen, save, scan, and optionally install in one flow
- Search across aliases, indexes, and discovered packages
- Interactive help and package picker when you run install with no arguments
- Install local wheels from a file or export directory
- Doctor --fix suggests commands to repair your setup
- Auto-alias prompt after browse or discover scan
- Install hints and defaults use short package names
- Trust prompt when a remote is unpinned
- Branch installs hint when a release wheel already exists
- CI test matrix covers Ubuntu, Windows, and macOS

### opip

- Prefers stable PyPI releases over prereleases (PEP 440)
- Install recovers from PEP 668 (venv, --user, or --target)
- --user retries with --break-system-packages on Arch-style PEP 668
- Refuses or recreates a venv when its Python version mismatches the bundle
- Filters incompatible wheels and rejects unreadable venv interpreters
- Update reinstalls with replace, restores dest/venv, can re-sign, reuses unchanged wheels
- Create from private indexes, find-links, offline wheel dirs, or lock files
  (uv.lock, poetry.lock, pip-tools hashed locks)
- SBOM is CycloneDX 1.5
- Extract to a wheelhouse or PEP 503 simple index
- Install backend choice: pip or uv
- JSON and quiet output for CI
- Trust uses the shared pip-rns trust store
- Delta and apply for thin update packs

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
