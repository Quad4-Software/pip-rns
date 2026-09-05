#!/usr/bin/env sh
# rngit release notes helper. $1 = temp notes file (rngit seeds it before calling EDITOR)
set -e

notes_file=$1
tag=${RELEASE_TAG:-}

if [ -z "$tag" ] && [ -f "$notes_file" ]; then
    tag=$(sed -n 's/^# Enter release notes for \(.*\)\.$/\1/p' "$notes_file" | head -1)
fi

if [ -z "$tag" ]; then
    root=$(cd "$(dirname "$0")/.." && pwd)
    ver=$(grep -E '^version = ' "$root/pyproject.toml" | sed 's/.*"\([^"]*\)".*/\1/')
    tag=v${ver}
fi

cat > "$notes_file" <<EOF
pip-rns ${tag}

Install Python packages directly from Reticulum rngit remotes
via pip, pipx, uv, or poetry.

EOF
