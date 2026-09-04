# pip-rns docs

These guides explain how to install packages over Reticulum and how to move wheels offline with opip.

You choose every source. Nothing ships with a vendor index. Indexes and aliases are opt-in.

## Tools

| Tool | Role |
|------|------|
| pip-rns / pipx-rns | Install from rngit remotes with pip, pipx, uv, or poetry |
| opip | Build, verify, and install offline .opip bundles |

## Read in order

1. [Getting started](getting-started.md) - install the tools and run a first command
2. [pip-rns](pip-rns.md) - remotes, releases, backends, and day-to-day installs
3. [opip](opip.md) - create and install integrity-backed wheel bundles
4. [Trust and signing](trust.md) - publishers, verification, and fail-closed behavior
5. [Discovery](discovery.md) - browse, discover, search, aliases, and indexes
6. [Sneakernet](sneakernet.md) - USB and air-gap paths end to end
7. [Troubleshooting](troubleshooting.md) - doctor, PEP 668, and common fixes

## Quick picks

Want a package from the mesh right now?

```bash
pip-rns browse --install
```

Need to hand someone a USB stick?

```bash
opip create -r requirements.txt -o ./pkg.opip
opip export ./pkg.opip -o /media/usb/pkg.opip
```

On the other machine:

```bash
opip verify /media/usb/pkg.opip --require-signature
opip install /media/usb/pkg.opip
```

## Also available

- Root [README](../README.md) for a compact reference
- pip-rns help and opip help (add -i for a menu)
- Man pages under man/man1/
