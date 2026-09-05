# Trust and signing

Both tools prefer verified artifacts. Signed release wheels and signed .opip bundles fail closed when verification cannot be confirmed, unless you explicitly opt into insecure mode.

## Mental model

1. Prefer a release wheel or a signed bundle over a raw source clone.
2. Pin publishers you rely on so installs do not ask every time.
3. Use --insecure only when you understand you are skipping checks.
4. On USB paths, verify before install.

## pip-rns trust store

Remember a publisher for a remote:

```bash
pip-rns trust add rns://identity/group/repo e46112d44649266d71fe2193e00a4710
pip-rns trust ls
```

One-off pin on install:

```bash
pip-rns install --from-release rns://identity/group/repo \
  --ref v1.0.0 \
  --verify e46112d44649266d71fe2193e00a4710
```

Default identity when a remote has no stored pin:

```bash
pip-rns trust set-default e46112d44649266d71fe2193e00a4710
pip-rns trust forget-default
pip-rns trust rm rns://identity/group/repo
```

Store path: ~/.config/pip-rns/trust.json (or under PIP_RNS_CONFIG).

When --verify is omitted, pip-rns uses the trust store unless --insecure is set.

## Unpinned remotes

On a TTY, an unpinned remote can prompt you to trust and remember the publisher. In CI or with --no-interactive, pass --verify, rely on a stored pin, or use --insecure deliberately.

## Release signatures

rngit release artifacts may include .rsg sidecars (and .rsm manifests). Signed releases must verify. If verification fails or cannot run, the install stops.

Skip only when you mean it:

```bash
pip-rns install --from-release rns://identity/group/repo --ref v1.0.0 --insecure
```

Manual check with rnid for a published wheel signature:

```bash
rnid -i e46112d44649266d71fe2193e00a4710 -V pip_rns-*.rsg
```

## opip signatures

Generate an identity and sign at create time:

```bash
opip keygen -o publisher.rns
opip create -r requirements.txt --identity publisher.rns --publisher "My Team"
```

Verify with a required signer:

```bash
opip verify ./pkg.opip --signer e46112d44649266d71fe2193e00a4710 --require-signature
opip install ./pkg.opip --signer e46112d44649266d71fe2193e00a4710
```

opip uses the same trust store as pip-rns. When --signer is omitted, verify and install resolve a pin from trust.json (per-remote, then default):

```bash
opip trust add default e46112d44649266d71fe2193e00a4710
opip trust ls
opip verify ./pkg.opip --require-signature
```

Environment defaults:

- OPIP_IDENTITY for create
- OPIP_SIGNER for verify and install
- PIP_RNS_CONFIG for the shared trust store directory

## Bundles through pip-rns

```bash
pip-rns bundle verify ./pkg.opip --require-signature
pip-rns bundle install ./pkg.opip --signer e46112d44649266d71fe2193e00a4710
```

## Practical habits

- Treat --insecure as temporary and local, not a default in scripts.
- Prefer --require-release or --from-release when a project publishes wheels.
- Prefer --require-signature on air-gap machines after USB copy.
- Keep publisher identities in the trust store or in deployment docs next to the remote URL.

Next: move verified artifacts offline in [sneakernet](sneakernet.md).
