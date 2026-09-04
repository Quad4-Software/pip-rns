# Getting started

pip-rns installs Python packages from Reticulum remotes you choose. opip packs and installs offline wheel bundles for USB or air-gap machines. Both ship in one package.

## Requirements

- Python 3.7 or newer
- For mesh install and discover: a working Reticulum stack and the rns package
- For rngit remotes: rngit on your PATH
- At least one install backend: pip, pipx, uv, or poetry

opip itself uses only the Python standard library.

## Install pip-rns

From a local wheel:

```bash
pip install pip_rns-*.whl
```

From source over rngit:

```bash
git clone rns://06a54b505bb67b25ef3f8097e8001edc/public/pip-rns
cd pip-rns
make
make install
```

Optional HTTPS bridges when you need them:

```bash
pip install pip-rns
# or
pipx install pip-rns
# or
pip install git+https://github.com/Quad4-Software/pip-rns
```

Check that the CLIs are on your PATH:

```bash
pip-rns --version
opip --version
pipx-rns --version
```

## First useful checks

Run doctor before you rely on the mesh:

```bash
pip-rns doctor
opip doctor
```

Add --fix if something looks wrong and you want repair hints:

```bash
pip-rns doctor --fix
```

Optional live check against a remote:

```bash
pip-rns doctor --online --remote rns://identity/group/repo
```

## Shell completions

```bash
pip-rns completion install
opip completion install
```

Pick a shell if detection is wrong:

```bash
pip-rns completion install --shell zsh
```

## Your first install paths

### Offline first

On a machine with network access, build a bundle, then move the file:

```bash
opip create -r requirements.txt -o ./pkg.opip
```

Copy pkg.opip to the target host, then:

```bash
opip verify ./pkg.opip
opip install ./pkg.opip
```

### Mesh install by short name

Listen, scan, and install in one flow:

```bash
pip-rns browse --install
```

Or install a name you already know:

```bash
pip-rns install lxmfy
```

### Direct remote

```bash
pip-rns install rns://identity/group/repo
# pin a release
pip-rns install rns://identity/group/repo@v1.0.0
```

On a TTY with no mode flags, pip-rns offers a menu. Latest release is preferred. A full source clone is labeled as expensive.

## Source preference (cheapest first)

1. Local .opip or exported .whl (no RNS needed)
2. Signed release wheel over RNS
3. Source clone over RNS (cached after the first pull)
4. Opt-in indexes you register yourself

There is no default vendor index. Add only remotes and indexes you trust.

## Where next

- Day-to-day remotes and backends: [pip-rns](pip-rns.md)
- Bundles and air-gap installs: [opip](opip.md)
- Publishers and verification: [trust](trust.md)
