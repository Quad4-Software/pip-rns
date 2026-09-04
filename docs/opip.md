# opip

opip builds integrity-backed offline wheel bundles (.opip) and installs them on machines that may never touch the public internet.

A bundle holds wheels, a pinned requirements list, and metadata used for verify and provenance checks.

## What is inside a bundle

Typical contents:

- manifest.json - what the bundle claims to be
- integrity.json - hashes for the packed files
- lock.json - resolved pins (opip-lock/1)
- sbom.json - CycloneDX 1.5 SBOM
- optional publisher.json
- wheels/ plus pinned requirements.txt
- optional .rsg sidecar (Reticulum signature)
- optional .rsm when published via rngit release

## Create

From the current project (reads pyproject.toml, setup.py, requirements.txt, or a lockfile):

```bash
opip create
```

From an explicit requirements file:

```bash
opip create -r requirements.txt -o ./pkg.opip
```

From a lockfile as source of truth (no live version resolution):

```bash
opip create --lockfile uv.lock -o ./pkg.opip
opip create --lockfile poetry.lock
opip create --lockfile requirements.lock
```

Pass `--no-lock` to ignore an auto-detected lockfile.

Target a Python and platform:

```bash
opip create -r requirements.txt --python 3.12 --platform win_amd64
```

One file for Windows, Linux, and macOS:

```bash
opip create -r requirements.txt --python 3.12 --platform universal
```

Private index or mirror (Warehouse JSON API):

```bash
opip create -r requirements.txt --index-url https://pypi.example/pypi
```

Air-gap create from a local wheel directory (no network):

```bash
opip create -r requirements.txt --find-links /media/usb/wheels --offline
```

## Sign while creating

```bash
opip keygen -o publisher.rns
opip create -r requirements.txt \
  --publisher "My Team" \
  --identity publisher.rns \
  --require-pypi-hash
```

Publish as an rngit release (creates an .rsm alongside):

```bash
rngit release -i publisher.rns rns://identity/group/repo create v1.0.0:./dist
```

## Verify

Always verify before install when the file came from elsewhere:

```bash
opip verify ./pkg.opip
opip verify ./pkg.opip --signer e46112d44649266d71fe2193e00a4710
opip verify ./pkg.opip --require-signature
```

A present .rsg is checked via the embedded pubkey. Pass --signer to pin the identity you expect. When `--signer` is unset, opip uses the shared pip-rns trust store (default or per-remote pin).

## CI / automation

```bash
opip --no-interactive -y verify ./pkg.opip --require-signature --signer IDENTITY
opip --json verify ./pkg.opip --require-signature
opip --quiet install ./pkg.opip --venv .venv -y
```

Also: `CI=1`, `OPIP_NO_INTERACTIVE=1`, or a non-TTY. Exit codes: 0 ok, 1 failure, 2 usage.

`--json` works on verify, info, list, and trust ls. `--quiet` / `-q` suppresses success stdout.

## Install

From a local file:

```bash
opip install ./pkg.opip
```

Into a venv:

```bash
opip install ./pkg.opip --venv .venv
```

With uv instead of pip:

```bash
opip install ./pkg.opip --venv .venv --backend uv
```

Default backend is pip. If a venv has no pip and uv is on PATH, install falls back to uv.

Into a specific directory:

```bash
opip install ./pkg.opip --target /opt/wheels
opip install ./pkg.opip --target /opt/wheels --remember-target
```

User site (automatically adds --break-system-packages when PEP 668 blocks --user):

```bash
opip install ./pkg.opip --user
```

From Reticulum (release or path inside a release):

```bash
opip install rns://identity/group/repo@v1.0.0
opip install rns://identity/group/repo@v1.0.0:my-bundle.opip
```

HTTP, HTTPS, FTP, and git sources are also accepted when you need a bridge.

On PEP 668 protected interpreters, install can prompt for a venv, --user, or --target recovery path. The bundle Python version must match the current interpreter. An existing venv with the wrong Python is refused or recreated after confirmation.

## Hand-off for other package managers

`.opip` is not a pip/uv/poetry format. Extract wheels first:

```bash
opip extract ./pkg.opip -o ./wheelhouse --require-signature
pip install --no-index --find-links ./wheelhouse -r ./wheelhouse/requirements.txt
```

Optional PEP 503 simple index layout:

```bash
opip extract ./pkg.opip -o ./wheelhouse --simple-index
pip install --no-index --index-url file://$PWD/wheelhouse package-name
```

## Export for USB

```bash
opip export ./pkg.opip -o /media/usb/pkg.opip
```

Export verifies before copying.

## Delta packs (scarce updates)

Ship only changed wheels after the base bundle is already on the far side:

```bash
opip delta ./pkg-v1.opip ./pkg-v2.opip -o ./pkg-v1-to-v2.opipd
opip apply ./pkg-v1.opip ./pkg-v1-to-v2.opipd -o ./pkg-v2.opip
```

`apply` fails closed if the base file hash does not match the delta.

## Trust store

Same store as pip-rns (`~/.config/pip-rns/trust.json`):

```bash
opip trust add default e46112d44649266d71fe2193e00a4710
opip trust ls
opip trust rm default
```

## Manage registered bundles

```bash
opip list
opip list installed
opip info ./pkg.opip
opip --json info ./pkg.opip
opip update nomadnet
opip update nomadnet --venv .venv
opip update nomadnet --no-reinstall -o ./nomadnet-new.opip
opip update nomadnet --emit-delta ./nomadnet.patch.opipd
opip uninstall nomadnet
```

`opip update` rebuilds from pinned requirements, reuses unchanged wheels from the previous bundle when hashes match, then reinstalls with upgrade/force-reinstall into the previous destination when known. Pass `--identity` to re-sign if the old bundle was signed.

Remembered destinations:

```bash
opip dest list
opip dest set my-bundle /opt/wheels
opip dest forget my-bundle
```

## Windows helpers

```bash
opip register-windows
```

Registers the .opip file association and Explorer context menus. Double-click uses the interactive open flow.

## Doctor and help

```bash
opip doctor
opip help
opip help create
opip help -i
```

## Environment

```text
OPIP_DATA_DIR       state directory (same as --data-dir)
OPIP_JOBS           parallel downloads for create
OPIP_PYTHON         default --python
OPIP_PLATFORM       default --platform
OPIP_PUBLISHER      default --publisher
OPIP_IDENTITY       default identity path for signing
OPIP_SIGNER         default --signer for verify and install
OPIP_INDEX_URL      Warehouse JSON index base for create
OPIP_FIND_LINKS     local wheel directory for create
OPIP_OFFLINE        refuse network during create when set
OPIP_BACKEND        install backend: pip or uv
OPIP_COLOR          auto, always, or never
OPIP_NO_INTERACTIVE disable prompts
PIP_RNS_CONFIG      aliases and shared trust store
```

Global flags include --data-dir, --config, --no-color, --no-interactive / -y, --json, --quiet / -q, and --version.

## Next

- End-to-end USB flow: [sneakernet](sneakernet.md)
- Signer pins and fail-closed rules: [trust](trust.md)
