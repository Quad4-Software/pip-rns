#!/usr/bin/env sh
# rngit release notes editor script
# $1 = path to temp file with release notes template
cat > "$1" <<EOF
pip-rns v1.0.0

Install Python packages directly from Reticulum rngit remotes
via pip, pipx, uv, or poetry.

EOF
