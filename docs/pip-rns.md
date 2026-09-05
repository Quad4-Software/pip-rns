# pip-rns

pip-rns resolves a remote (or alias, index name, discovery hit, or local wheel), then hands the artifact to pip, pipx, uv, or poetry.

pipx-rns is the same flow with pipx as the default backend, plus inject.

## Install shapes

Bare remote (install is implied):

```bash
pip-rns rns://identity/group/repo
```

Explicit install with a tag:

```bash
pip-rns install rns://identity/group/repo --ref v1.0.0
# same idea
pipx-rns install identity/group/repo@v1.0.0
```

Prefer a release wheel (no build step):

```bash
pip-rns install --from-release rns://identity/group/repo --ref v1.0.0
```

Force a source clone:

```bash
pip-rns install --from-source rns://identity/group/repo
# short form
pip-rns install -s rns://identity/group/repo
```

Require a release wheel or fail:

```bash
pip-rns install --require-release rns://identity/group/repo --ref v1.0.0
```

Branch-like refs such as @master or @main clone from source automatically.

## Local wheels

After pip-rns export or a USB mirror:

```bash
pip-rns install /media/usb/pkg-1.0.0-py3-none-any.whl
pip-rns install /media/usb/mirror
```

## Backends

Default is pip. Switch with a flag:

```bash
pip-rns install --pipx identity/group/repo
pip-rns install --uv identity/group/repo
pip-rns install --poetry identity/group/repo
```

Or use the pipx entry point:

```bash
pipx-rns install identity/group/repo
pipx-rns inject my-app identity/group/repo
```

Flags after -- go to the backend:

```bash
pip-rns install identity/group/repo -- --break-system-packages
pip-rns install --poetry identity/group/repo -- --dev
pipx-rns install identity/group/repo -- --force
```

## Releases

List and inspect:

```bash
pip-rns release list rns://identity/group/repo
pip-rns release view rns://identity/group/repo v1.0.0
```

Export wheels for USB:

```bash
pip-rns export rns://identity/group/repo --ref v1.0.0 -o /media/usb/mirror
```

Signed releases fail closed unless verification succeeds. Pass --insecure only when you knowingly skip that check. See [trust](trust.md).

## Offline and cache

Use cache and local paths only (no RNS fetch):

```bash
pip-rns install --offline rns://identity/group/repo
```

RNS source installs reuse ~/.local/share/pip-rns/cache when possible. Set PIP_RNS_NO_CACHE=1 to force a fresh temp clone.

Editable checkout:

```bash
pip-rns install --editable rns://identity/group/repo
```

## Destinations and venvs

```bash
pip-rns install identity/group/repo --venv /path/to/venv --remember-venv
pip-rns venv list
pip-rns venv set default /path/to/venv
pip-rns venv forget default
```

## Update, list, uninstall

```bash
pip-rns update rns://identity/group/repo
pip-rns update rns://identity/group/repo --from-release --ref v1.2.0
pip-rns update rns://identity/group/repo --venv .venv
pip-rns list
pip-rns uninstall some-package
```

pip-rns update is a fresh reinstall from the remote (same options as install). Prefer --from-release when a wheel exists.

Add --pipx, --uv, or --poetry when the install used that backend.

## Bundles via pip-rns

```bash
pip-rns bundle install lxmfy-bundle@v1.0.0 --signer e46112d44649266d71fe2193e00a4710
pip-rns bundle verify ./my-bundle.opip --require-signature
```

## Non-interactive / CI

```bash
pip-rns --no-interactive install rns://identity/group/repo --from-release --ref v1.0.0 -y
```

Or set PIP_RNS_NO_INTERACTIVE=1 or CI=1.

## Environment

```text
PIP_RNS_PIP             pip command (default pip)
PIP_RNS_PIPX            pipx command
PIP_RNS_UV              uv command
PIP_RNS_POETRY          poetry command
PIP_RNS_CONFIG          config directory for aliases and trust
PIP_RNS_USE_CACHE       set to 1 to enable cache
PIP_RNS_COLOR           auto, always, or never
PIP_RNS_NO_INTERACTIVE  disable prompts
NO_COLOR / FORCE_COLOR  standard color controls
```

Config lives under ~/.config/pip-rns/ (or %APPDATA%/pip-rns on Windows).

## Command map

```text
pip-rns [install] <remote> [options]
pip-rns browse | search | discover | export | trust | alias | index
pip-rns release | venv | bundle | doctor | completion | help | update
pip-rns list | uninstall
```

For short names, aliases, and indexes, see [discovery](discovery.md).
