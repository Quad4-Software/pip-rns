# opip

opip builds integrity-backed offline wheel bundles (.opip) and installs them on machines that may never touch the public internet.

A bundle holds wheels, a pinned requirements list, and metadata used for verify and provenance checks.

## What is inside a bundle

Typical contents:

- manifest.json - what the bundle claims to be
- integrity.json - hashes for the packed files
- lock.json - resolved pins
- sbom.json - software bill of materials style listing
- optional publisher.json
- wheels/ plus pinned requirements.txt
- optional .rsg sidecar (Reticulum signature)
- optional .rsm when published via rngit release

## Create

From the current project (reads pyproject.toml, setup.py, or requirements.txt):

```bash
opip create
```

From an explicit requirements file:

```bash
opip create -r requirements.txt -o ./pkg.opip
```

Target a Python and platform:

```bash
opip create -r requirements.txt --python 3.12 --platform win_amd64
```

One file for Windows, Linux, and macOS:

```bash
opip create -r requirements.txt --python 3.12 --platform universal
```

Named packages on the command line also work when you do not want a requirements file.

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

A present .rsg is checked via the embedded pubkey. Pass --signer to pin the identity you expect.

## Install

From a local file:

```bash
opip install ./pkg.opip
```

Into a venv:

```bash
opip install ./pkg.opip --venv .venv
```

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

## Export for USB

```bash
opip export ./pkg.opip -o /media/usb/pkg.opip
```

Export verifies before copying.

## Manage registered bundles

```bash
opip list
opip list installed
opip info ./pkg.opip
opip update nomadnet
opip update nomadnet --venv .venv
opip update nomadnet --no-reinstall -o ./nomadnet-new.opip
opip uninstall nomadnet
```

`opip update` rebuilds the registered `.opip` from its pinned requirements (needs network), then reinstalls with upgrade/force-reinstall into the previous destination when known (venv, --target, or --user). Pass `--identity` to re-sign if the old bundle was signed.

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
OPIP_COLOR          auto, always, or never
OPIP_NO_INTERACTIVE disable prompts
PIP_RNS_CONFIG      resolve pip-rns aliases for rns:// installs
```

Global flags include --data-dir, --no-color, --no-interactive / -y, and --version.

## Next

- End-to-end USB flow: [sneakernet](sneakernet.md)
- Signer pins and fail-closed rules: [trust](trust.md)
