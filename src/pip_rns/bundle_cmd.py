"""pip-rns bundle subcommand: install and verify .opip bundles via opip."""

from __future__ import annotations

import argparse
import os

from .aliases import init as alias_init
from .indexes import init as index_init
from .ui import bold, green, header, success


def register_parsers(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser(
        "bundle",
        help="Install or verify offline .opip bundles (via opip)",
    )
    bp = p.add_subparsers(dest="bundle_command", required=True)

    bi = bp.add_parser("install", help="Install a .opip bundle from any source")
    bi.add_argument(
        "source",
        help="Bundle path, rns:// remote, URL, git source, or pip-rns alias",
    )
    bi.add_argument("--target", default=None, help="Install into directory")
    bi.add_argument("--user", action="store_true", help="Install to user site-packages")
    bi.add_argument("--replace", action="store_true", help="Force reinstall packages")
    bi.add_argument("--no-verify", action="store_true", help="Skip integrity checks")
    bi.add_argument(
        "--signer",
        metavar="IDENTITY",
        default=None,
        help="Require bundle signed by IDENTITY (env: OPIP_SIGNER)",
    )
    bi.add_argument(
        "--require-signature",
        action="store_true",
        help="Fail if bundle is not signed",
    )

    bv = bp.add_parser("verify", help="Verify a .opip bundle")
    bv.add_argument("bundle", help="Path to .opip bundle file")
    bv.add_argument(
        "--signer",
        metavar="IDENTITY",
        default=None,
        help="Required signer identity hash or file (env: OPIP_SIGNER)",
    )
    bv.add_argument(
        "--require-signature",
        action="store_true",
        help="Fail if bundle is not signed",
    )


def _boot(config_dir: str | None) -> None:
    alias_init(config_dir)
    index_init()


def dispatch(args, config_dir: str | None) -> None:
    from opip.config import apply_defaults
    from opip.install import InstallError, install_from_source
    from opip.storage import Store
    from opip.verify import verify_bundle_file

    _boot(config_dir)
    apply_defaults(args)

    if args.bundle_command == "install":
        print(f"{header('⤵ Bundle')} {bold(args.source)}")
        store = Store(data_dir=getattr(args, "data_dir", None))
        try:
            packages = install_from_source(
                args.source,
                target=args.target,
                user=args.user,
                replace=args.replace,
                store=store,
                verify=not args.no_verify,
                signer=args.signer or os.environ.get("OPIP_SIGNER"),
                require_signature=args.require_signature,
            )
        except InstallError as exc:
            print(str(exc))
            raise SystemExit(1) from exc
        print(f"  {green('installed')} {len(packages)} package(s)")
        print(f"{success('✓ Done')}")
        return

    if args.bundle_command == "verify":
        ok, errors, _manifest = verify_bundle_file(
            args.bundle,
            signer=args.signer or os.environ.get("OPIP_SIGNER"),
            require_signature=args.require_signature,
        )
        if not ok:
            print("Verification failed:")
            for err in errors:
                print(f"  - {err}")
            raise SystemExit(1)
        print(f"{success('✓ Bundle verified')}")
