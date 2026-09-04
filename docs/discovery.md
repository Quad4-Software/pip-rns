# Discovery

When remotes announce on Reticulum, you can listen, scan for Python packages, search by short name, and install without typing full rns:// paths.

Resolution order for a short name:

1. Local aliases
2. Synced indexes you registered
3. Packages found by discovery scan

Nothing is pre-selected. You only see nodes that announce while you listen, and indexes you add yourself.

## Browse (one command)

Listen, save, scan, optionally alias, and install:

```bash
pip-rns browse --install
```

Useful flags:

```bash
pip-rns browse --seconds 60 --auto-alias
pip-rns browse --no-listen --no-scan
```

--auto-alias can offer short names after a successful scan. Browse needs a local Reticulum stack and the rns Python package for live listen.

## Discover step by step

Listen and store heard nodes:

```bash
pip-rns discover --seconds 60 --save
pip-rns discover ls
```

Scan stored nodes for packages (Nomad catalog when enabled, common packages index repos, release wheel checks):

```bash
pip-rns discover --save --scan
# or later
pip-rns discover scan
pip-rns discover packages
```

Clear stored discovery data when it goes stale:

```bash
pip-rns discover clear
```

Heard destination hashes can be used as rns://DESTINATION_HASH/group/repo when you know the path.

## Search

Search across aliases, indexes, and discovery:

```bash
pip-rns search lxm
pip-rns search reticulum
```

Then install by the short name that matched:

```bash
pip-rns install lxmfy
```

## Aliases

Save long remotes under short names:

```bash
pip-rns alias add lxmfy 06a54b505bb67b25ef3f8097e8001edc/public/LXMFy
pip-rns alias ls
pip-rns alias set lxmfy rns://identity/group/LXMFy
pip-rns alias rm lxmfy
```

Storage: ~/.config/pip-rns/aliases (or under PIP_RNS_CONFIG / --config).

Example file format:

```text
lxmfy=06a54b505bb67b25ef3f8097e8001edc/public/LXMFy
```

## Indexes (opt-in)

An index is an rngit repo with a packages listing. Register only remotes you trust:

```bash
pip-rns index add rns://identity/group/index
pip-rns index sync
pip-rns index ls
pip-rns index list
pip-rns index search lxmfy
pip-rns index rm rns://identity/group/index
```

After sync, short names from that index resolve like aliases (aliases still win first).

## Interactive install help

With no arguments on a TTY:

```bash
pip-rns install
```

You get interactive help and a package picker when discovery or aliases have candidates.

## Cost awareness

Full source clones over RNS are expensive. Prefer:

- release wheels (--from-release / auto when a release exists)
- exported local wheels
- cached source trees on repeat installs

pip-rns warns and confirms before the first expensive pull when it can.

## Related

- Install flags and backends: [pip-rns](pip-rns.md)
- Publisher pins: [trust](trust.md)
