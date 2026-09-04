# Sneakernet

Move packages without relying on the destination host having live RNS or HTTPS. Build or export on a connected machine, copy media, verify, then install.

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

## Checklist

1. Build or export on a machine you trust.
2. Prefer signed artifacts.
3. Copy the file, not a half-written download.
4. Verify on the destination before install.
5. Install into a venv or remembered --target when PEP 668 blocks system pip.
6. Keep the publisher identity written down next to the media label.

## Mixing with aliases

On the connected host you may resolve by short name. On the air-gap host, prefer the concrete file path unless you also copied config or use full remotes that already exist in cache.

```bash
# connected
pip-rns export lxmfy --ref v1.0.0 -o /media/usb/mirror
# air-gap
pip-rns install /media/usb/mirror
```

## Related

- Bundle commands: [opip](opip.md)
- Signing details: [trust](trust.md)
- When verify or install fails: [troubleshooting](troubleshooting.md)
