# Copyright (c) 2026, Quad4 (quad4.io)
"""Interactive and per-command help for opip."""

import argparse
import sys

from opip import __version__, terminal
from opip.config import COMMAND_SUMMARY, ENV_HELP, EXAMPLES


def show_main_help():
    """Print the main colored help overview."""
    terminal.heading(f"opip {__version__}")
    terminal.write_out(
        terminal.dim("Offline Python wheel bundles with integrity verification."),
    )
    terminal.write_out("")
    terminal.heading("Commands")
    for name, desc in COMMAND_SUMMARY:
        terminal.bullet(name.ljust(18), desc)
    terminal.write_out("")
    terminal.heading("Quick examples")
    for cmd, desc in EXAMPLES:
        terminal.bullet(terminal.bold(cmd), terminal.dim(desc))
    terminal.write_out("")
    terminal.heading("Environment")
    for name, desc in ENV_HELP:
        terminal.bullet(name, desc)
    terminal.write_out("")
    terminal.info("Run opip help <command> or opip <command> --help for details.")
    terminal.info(
        "Global flags: --data-dir, --no-color, --no-interactive/-y, --version",
    )


def show_command_help(parser, command_name):
    """Print colored argparse help for one subcommand."""
    subparsers_action = None
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            subparsers_action = action
            break
    if subparsers_action is None or command_name not in subparsers_action.choices:
        terminal.error(f"Unknown command: {command_name}")
        terminal.info("Run opip help for a list of commands.")
        return 1

    subparser = subparsers_action.choices[command_name]
    terminal.heading(f"opip {command_name}")
    terminal.write_out("")
    help_text = subparser.format_help()
    terminal.write_out(_colorize_help_text(help_text))
    return 0


def _colorize_help_text(text):
    if not terminal.enabled():
        return text
    lines = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("opip ") and "usage:" not in line.lower():
            lines.append(terminal.bold(line))
        elif stripped.startswith("usage:"):
            lines.append(terminal.cyan(line))
        elif stripped.startswith("-"):
            lines.append(terminal.yellow(line))
        elif stripped.endswith(":") and not stripped.startswith(" "):
            lines.append(terminal.bold(line))
        else:
            lines.append(line)
    return "\n".join(lines)


def interactive_help(parser, no_interactive=False):
    """TTY menu to browse commands."""
    show_main_help()
    from opip.interactive import is_noninteractive

    if is_noninteractive(no_interactive):
        return 0

    names = [name for name, _desc in COMMAND_SUMMARY if name != "help"]
    terminal.write_out("")
    terminal.heading("Interactive help")
    terminal.info("Enter a command name or number for details, or q to quit.")
    while True:
        for idx, name in enumerate(names, 1):
            terminal.write_out(f"  {idx}. {terminal.cyan(name)}")
        terminal.write_out("")
        sys.stdout.write(terminal.dim("help> "))
        sys.stdout.flush()
        try:
            choice = input().strip()
        except (EOFError, KeyboardInterrupt):
            terminal.write_out("")
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
            terminal.write_out("")
            show_command_help(parser, choice)
            terminal.write_out("")
            continue

        terminal.warn(f"Unknown choice: {choice}")
