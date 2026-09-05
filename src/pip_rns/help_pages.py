# Copyright (c) 2026, Quad4 (quad4.io)
"""Interactive and per-command help for pip-rns."""

from __future__ import annotations

import argparse
import sys

from opip.interactive import is_noninteractive

from .ui import bold, cyan, dim, header, yellow
from .version import __version__

COMMAND_SUMMARY = [
    ("install", "Install from remote, alias, or local .whl"),
    ("browse", "Listen, scan, and browse mesh packages"),
    ("search", "Search aliases, indexes, and discovery"),
    ("discover", "Listen for rngit nodes on Reticulum"),
    ("export", "Mirror release wheels for sneakernet"),
    ("self-install", "Install pip-rns/opip without system pip"),
    ("trust", "Remember release publisher identities"),
    ("alias", "Short names for long remotes"),
    ("index", "Opt-in package indexes"),
    ("bundle", "Install or verify .opip offline bundles"),
    ("doctor", "Environment health checks"),
    ("help", "This help"),
]

EXAMPLES = [
    ("pip-rns help bootstrap", "No-pip / zipapp recipes"),
    ("pip-rns browse --install", "Discover and install interactively"),
    ("pip-rns install lxmfy", "Install by short name"),
    ("pip-rns install ./pkg.whl", "Install exported wheel from USB"),
    ("python3 pip-rns.pyz self-install --user", "Install tools without pip"),
    ("pip-rns export rns://id/g/repo -o /media/usb", "Mirror for sneakernet"),
]

ENV_HELP = [
    ("PIP_RNS_CONFIG", "Config directory for aliases and trust"),
    ("PIP_RNS_NO_INTERACTIVE", "Disable prompts"),
    ("PIP_RNS_COLOR", "auto, always, or never"),
]


def show_main_help() -> None:
    print(header(f"pip-rns {__version__}"))
    print(dim("Install Python packages from Reticulum remotes you choose."))
    print()
    print(header("Commands"))
    for name, desc in COMMAND_SUMMARY:
        print(f"  {bold(name.ljust(14))} {dim(desc)}")
    print()
    print(header("Quick examples"))
    for cmd, desc in EXAMPLES:
        print(f"  {bold(cmd)}")
        print(f"    {dim(desc)}")
    print()
    print(header("Environment"))
    for name, desc in ENV_HELP:
        print(f"  {name}")
        print(f"    {dim(desc)}")
    print()
    print(dim("Run pip-rns help <command> or pip-rns <command> --help for details."))


def show_command_help(parser: argparse.ArgumentParser, command_name: str) -> int:
    subparsers_action = None
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            subparsers_action = action
            break
    if subparsers_action is None or command_name not in subparsers_action.choices:
        print(f"Unknown command: {command_name}", file=sys.stderr)
        print(dim("Run pip-rns help for a list of commands."))
        return 1

    subparser = subparsers_action.choices[command_name]
    print(header(f"pip-rns {command_name}"))
    print()
    print(subparser.format_help())
    return 0


def interactive_help(
    parser: argparse.ArgumentParser,
    *,
    no_interactive: bool = False,
) -> int:
    show_main_help()
    if is_noninteractive(no_interactive):
        return 0

    names = [name for name, _desc in COMMAND_SUMMARY if name != "help"]
    print()
    print(header("Interactive help"))
    print(dim("Enter a command name or number for details, or q to quit."))
    while True:
        for idx, name in enumerate(names, 1):
            print(f"  {idx}. {cyan(name)}")
        print()
        try:
            choice = input(f"{dim('help> ')}").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0

        if not choice or choice.lower() in ("q", "quit", "exit"):
            return 0

        if choice.isdigit():
            num = int(choice)
            if 1 <= num <= len(names):
                choice = names[num - 1]

        if choice == "help":
            show_main_help()
            continue

        if choice in names:
            print()
            show_command_help(parser, choice)
            print()
            continue

        print(f"{yellow('unknown choice:')} {choice}")
