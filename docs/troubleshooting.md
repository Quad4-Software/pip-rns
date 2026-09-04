# Troubleshooting

Start with doctor. Fix what it reports before chasing mesh or signature issues.

## Doctor

```bash
pip-rns doctor
pip-rns doctor --fix
opip doctor
```

Online probe when remotes should be reachable:

```bash
pip-rns doctor --online --remote rns://identity/group/repo
```

## PEP 668 (externally managed environment)

System Python may refuse installs. opip and pip-rns can prompt for recovery when interactive:

- create or use a virtualenv
- install with --user when that is acceptable
- install with --target into a directory you control

Non-interactive example with an explicit target:

```bash
opip install ./pkg.opip --target "$HOME/.local/opip-target"
pip-rns install ./pkg.whl --venv "$HOME/.venvs/app"
```

Remember destinations to avoid repeating the path:

```bash
opip install ./pkg.opip --target /opt/wheels --remember-target
pip-rns install pkg --venv /path/to/venv --remember-venv
```

## Signature or trust failures

Symptoms: install stops on a signed release or bundle.

Checks:

```bash
pip-rns trust ls
opip verify ./pkg.opip --require-signature
opip verify ./pkg.opip --signer YOUR_IDENTITY_HEX --require-signature
```

Fixes:

- add the publisher with pip-rns trust add
- pass --verify or --signer with the correct identity
- confirm the .rsg sidecar traveled with the artifact
- only then consider --insecure for a one-off debug install

## Discovery hears nothing

- Confirm Reticulum is up and the rns package imports
- Widen the listen window:

```bash
pip-rns discover --seconds 120 --save
```

- Nodes must announce git.repositories during that window
- Discovery is passive. Silence usually means nobody announced nearby

Then scan:

```bash
pip-rns discover scan
pip-rns discover packages
```

## Short name not found

Resolution order is aliases, then indexes, then discovery packages.

```bash
pip-rns alias ls
pip-rns index sync
pip-rns index list
pip-rns discover packages
pip-rns search yourquery
```

Add an alias if you know the remote:

```bash
pip-rns alias add shortname identity/group/repo
```

## Expensive clone / branch installs

Branch refs clone source. Prefer a release when one exists:

```bash
pip-rns release list rns://identity/group/repo
pip-rns install --from-release rns://identity/group/repo --ref v1.0.0
```

Cache reuse lives under ~/.local/share/pip-rns/cache. Force a fresh clone with PIP_RNS_NO_CACHE=1 only when debugging.

## Offline install misses artifacts

--offline never contacts RNS. Export again on a connected host, or drop --offline if a fetch is acceptable.

```bash
pip-rns export rns://identity/group/repo --ref v1.0.0 -o ./mirror
pip-rns install --offline ./mirror
```

## Completions or color oddities

```bash
pip-rns completion install --shell zsh
```

Color settings:

```text
PIP_RNS_COLOR=never
OPIP_COLOR=never
NO_COLOR=1
FORCE_COLOR=1
```

Classic Windows consoles stay colorless unless Windows Terminal / ConEmu / ANSICON or FORCE_COLOR is set.

## Helpful exits

- Ctrl-C and prompt cancel exit cleanly
- Interactive command help:

```bash
pip-rns help -i
opip help -i
```

- Root [README](../README.md) for the compact command list

## Still stuck

1. Capture doctor output from both tools
2. Note whether the path is release, source, local wheel, or .opip
3. Note interactive vs CI (--no-interactive or CI=1)
4. Confirm the publisher identity you expect

Then re-read [trust](trust.md) or [sneakernet](sneakernet.md) for the path you are on.
