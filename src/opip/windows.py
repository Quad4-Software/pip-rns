"""Windows shell integration: file association and context menus."""

import os
import sys


import subprocess


class WindowsIntegrationError(Exception):
    pass


PROG_ID = "Opip.Bundle"
EXT = ".opip"


def _require_windows():
    if sys.platform != "win32":
        raise WindowsIntegrationError(
            "Windows integration is only available on Windows."
        )


def _launcher(prefix_args):
    exe = sys.executable
    module = "-m opip"
    return '"{0}" {1} {2} "%1"'.format(exe, module, prefix_args)


def register_windows():
    """Register .opip file association and Explorer context menus."""
    _require_windows()
    import winreg

    open_cmd = _launcher("open")
    install_cmd = _launcher("install")
    update_cmd = _launcher("install --replace")
    uninstall_cmd = _launcher("uninstall-file")
    verify_cmd = _launcher("verify")

    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, "Software\\Classes\\" + EXT) as ext_key:
        winreg.SetValue(ext_key, None, winreg.REG_SZ, PROG_ID)

    base = "Software\\Classes\\{0}".format(PROG_ID)
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, base) as prog_key:
        winreg.SetValue(prog_key, None, winreg.REG_SZ, "opip offline bundle")
        with winreg.CreateKey(prog_key, "DefaultIcon") as icon_key:
            winreg.SetValue(icon_key, None, winreg.REG_SZ, "{0},0".format(sys.executable))
        with winreg.CreateKey(prog_key, "shell\\open\\command") as open_key:
            winreg.SetValue(open_key, None, winreg.REG_SZ, open_cmd)

    _set_verb(base, "install", "Install with opip", install_cmd)
    _set_verb(base, "update", "Update with opip", update_cmd)
    _set_verb(base, "uninstall", "Uninstall with opip", uninstall_cmd)
    _set_verb(base, "verify", "Verify with opip", verify_cmd)

    return True


def unregister_windows():
    """Remove .opip file association and context menus."""
    _require_windows()
    import subprocess

    keys = [
        r"HKCU\Software\Classes\{0}\shell".format(PROG_ID),
        r"HKCU\Software\Classes\{0}".format(PROG_ID),
        r"HKCU\Software\Classes\{0}".format(EXT),
    ]
    for key in keys:
        subprocess.run(
            ["reg", "delete", key, "/f"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    return True


def _set_verb(base, verb, label, command):
    import winreg

    path = "{0}\\shell\\{1}".format(base, verb)
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, path) as verb_key:
        winreg.SetValue(verb_key, None, winreg.REG_SZ, label)
        with winreg.CreateKey(verb_key, "command") as cmd_key:
            winreg.SetValue(cmd_key, None, winreg.REG_SZ, command)
