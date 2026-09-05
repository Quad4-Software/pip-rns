# Sneakernet

Move packages without live RNS or HTTPS on the destination. Build or export on a connected machine, copy media, verify, then install.

## Path A: opip bundle

### Connected machine

```bash
cd /path/to/project
opip create -o ./pkg.opip
# or
opip create -r requirements.txt -o ./pkg.opip --platform universal
```

Sign if you will require a signature on the far side:

```bash
opip create -r requirements.txt -o ./pkg.opip \
  --identity publisher.rns \
  --publisher "My Team"
```

Copy for transport:

```bash
opip export ./pkg.opip -o /media/usb/pkg.opip
```

### Air-gap or USB target

```bash
opip verify /media/usb/pkg.opip --require-signature
opip install /media/usb/pkg.opip
```

Pin the expected identity when you know it:

```bash
opip verify /media/usb/pkg.opip --signer e46112d44649266d71fe2193e00a4710 --require-signature
opip install /media/usb/pkg.opip --signer e46112d44649266d71fe2193e00a4710
```

## Path B: release wheel mirror

### Connected machine

```bash
pip-rns export rns://identity/group/repo --ref v1.0.0 -o /media/usb/mirror
```

Optionally pin the publisher while exporting:

```bash
pip-rns export rns://identity/group/repo --ref v1.0.0 \
  --verify e46112d44649266d71fe2193e00a4710 \
  -o /media/usb/mirror
```

### Target machine

```bash
pip-rns install /media/usb/mirror/pkg-1.0.0-py3-none-any.whl
# or point at the export directory
pip-rns install /media/usb/mirror
```

Offline mode refuses RNS fetches if something is missing:

```bash
pip-rns install --offline /media/usb/mirror/pkg-1.0.0-py3-none-any.whl
```

## Path C: signed bundle from an rngit release

On the publisher side, create a signed .opip and attach it to a release. On the consumer:

```bash
opip install rns://identity/group/repo@v1.0.0
opip install rns://identity/group/repo@v1.0.0:my-bundle.opip
```

That path still needs RNS on the consumer. For true air-gap, copy the .opip file itself (Path A).

## Path D: delta packs after the base is already there

On the connected machine, after you already shipped pkg-v1.opip once:

```bash
opip create -r requirements.txt -o ./pkg-v2.opip
opip delta ./pkg-v1.opip ./pkg-v2.opip -o /media/usb/pkg-v1-to-v2.opipd
```

On the air-gap host that still has the base:

```bash
opip apply /media/usb/pkg-v1.opip /media/usb/pkg-v1-to-v2.opipd -o ./pkg-v2.opip
opip verify ./pkg-v2.opip --require-signature
opip install ./pkg-v2.opip
```

apply refuses a wrong base file (hash mismatch). Prefer this over copying a full universal bundle on every update.

## Path E: USB kit (no Python / no pip)

Ship a ready-to-run stick: zipapps, integrity-backed .opip bundles, optional portable CPython, an AppImage-style Run launcher, and get-opip.py.

### Zero prior tools (no pip online or offline, Tor, hand wheels)

1. Download a pip_rns wheel and get-opip.py in the browser (Tor), or copy get-opip.py as a text file.
2. Build zipapps from the wheel (no pip, no network):

```bash
python3 get-opip.py --from-wheel pip_rns-1.5.0-py3-none-any.whl -o .
```

3. Build the kit from wheels you already saved:

```bash
python3 opip.pyz kit create nomadnet -o /media/usb \
  --find-links ./wheels --offline \
  --with-runtime --as-app
```

Or fetch over Tor instead of hand wheels:

```bash
python3 opip.pyz kit create nomadnet -o /media/usb \
  --with-runtime --as-app \
  --proxy socks5h://127.0.0.1:9050
```

### Air-gap machine (AppImage-like)

```bash
/media/usb/NomadNet
# or
/media/usb/Run
```

Optional classic venv install:

```bash
/media/usb/install.sh
```

Release zipapps alone:

```bash
make pyz
python3 dist/opip.pyz --version
python3 get-opip.py --from-dir dist -o ~/bin
```

## Checklist

1. Build or export on a machine you trust.
2. Prefer signed artifacts (and signed zipapps when shipping kits).
3. Copy the file, not a half-written download.
4. Verify on the destination before install.
5. Install into a venv or remembered --target when PEP 668 blocks system pip.
6. Keep the publisher identity written down next to the media label.
7. After the first full bundle, prefer .opipd deltas for scarce links.
8. For hosts with no Python, use --with-runtime kits.

## Mixing with aliases

On the connected host you may resolve by short name. On the air-gap host, prefer the concrete file path unless you also copied config or use full remotes that already exist in cache.

```bash
# connected
pip-rns export lxmfy --ref v1.0.0 -o /media/usb/mirror
# air-gap
python3 pip-rns.pyz install /media/usb/mirror --offline
```

## Related

- Bundle commands: [opip](opip.md)
- Signing details: [trust](trust.md)
- When verify or install fails: [troubleshooting](troubleshooting.md)
