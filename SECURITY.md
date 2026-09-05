# Security Policy

## Supported versions

Security fixes are applied to the latest release on the default branch.
Older releases are not backported unless a fix is already trivial to cherry-pick.

## Reporting a vulnerability

Report vulnerabilities privately through GitHub Security Advisories for this
repository:

https://github.com/Quad4-Software/pip-rns/security/advisories/new

Do not open a public issue or pull request that describes an unfixed vulnerability.

Include as much as you can:

- Affected package or command (pip-rns, opip, or a script)
- Version or commit
- Steps to reproduce
- Impact (integrity, availability, or confidentiality)

## Disclosure and timelines

We aim to acknowledge private reports within 7 days and to share an initial
assessment within 14 days. When a report is valid, we open a private advisory,
work on a fix, and coordinate a public disclosure after a patched release is
available. Critical issues that already have a public exploit may be disclosed
sooner with mitigation guidance.

Credit is given to reporters who want it when the advisory is published.

## Scope

In scope: remote package install and resolve paths, zip and wheel handling,
offline kit and zipapp bootstrap, trust and signature checks, and CI release
artifacts.

Out of scope: vulnerabilities only in third-party packages you install through
this tool, and issues that require a compromised Reticulum peer you already
chose to trust.
