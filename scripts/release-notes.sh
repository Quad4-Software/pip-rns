#!/usr/bin/env sh
# rngit release notes editor script
# $1 = path to temp file with release notes template
cat > "$1" <<EOF
pip-rns v0.1.0

Install Python packages directly from Reticulum rns:// git remotes
via pip, pipx, uv, or poetry.

Features:
  - Multi-backend install (pip, pipx, uv, poetry)
  - Version pinning with @tag or --ref
  - Offline cache for air-gapped installs
  - Editable mode for persistent checkouts
  - pipx inject support
  - Local aliases for remote paths
  - Remote package indexes with sync/search
  - Automatic retry on transient failures

Install: pip install pip-rns
EOF
