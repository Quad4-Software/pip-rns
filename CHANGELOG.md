# Changelog

## 1.3.0

### Added

- Remembered install destinations for opip bundles (dest list set forget)
- Remembered virtualenvs for pip-rns (venv list set forget)
- doctor commands for pip-rns and opip
- completion install for bash zsh and fish
- Non-interactive mode for automation and CI
- Reticulum wait spinner on real terminals
- Install summary showing remote mode artifact dest and signer status
- Auto use of a release wheel when one exists (from-source and from-release overrides)
- Backend contract tests for pip pipx uv and poetry

### Changed

- Safer zip extract and wheel install (path escape and size limits)
- Integrity verify rejects escaped paths and unlisted files
- Artifact names sanitized for cache and download paths
- Present `.rsg` sidecars are verified by default via embedded pubkey (`--signer` pins identity)
- Release `.rsm`/`.rsg` verification is default via rngit (`--verify` pins identity)
- Installer failures (PEP 668, permissions, missing pip) show recovery hints and can prompt for a venv
- Branch-like refs (`@master`, `@main`) clone from source without a release probe
- Bare remotes prompt for install mode on a TTY (`pip-rns rns://…` works as install shorthand)
- RNS source installs reuse a local cache and fetch/update instead of full recloning
- Ctrl-C and prompt cancel exit cleanly (status 130)
- Clearer signature error text
- Colors off on classic Windows cmd PowerShell and CI unless forced
- uv update uses reinstall
- poetry editable add flag order fixed
- doctor online check requires a remote you pass (no default destination)

### Removed

- First-run prompt that offered a vendor package index

## 1.2.0

### Added

- opip offline wheel bundles (create verify install export update uninstall)
- Integrity hashes lock and SBOM in bundles
- Reticulum identity signing and verify
- Install from local files HTTP FTP git or rns remotes
- Windows Explorer open for .opip files
- pip-rns bundle install and verify
- Alias resolve for rns sources from opip
- Shell completions and man pages for pip-rns pipx-rns and opip
