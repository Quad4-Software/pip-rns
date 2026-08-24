"""Windows shell integration: file association and context menus."""

import subprocess
import sys


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
    return f'"{exe}" {module} {prefix_args} "%1"'


def register_windows():
    """Register .opip file association and Explorer context menus."""
    _require_windows()
    import winreg

    open_cmd = _launcher("open")
    install_cmd = _launcher("install")
    update_cmd = _launcher("install --replace")
    uninstall_cmd = _launcher("uninstall-file")
    verify_cmd = _launcher("verify")

    with winreg.CreateKey(
        winreg.HKEY_CURRENT_USER, "Software\\Classes\\" + EXT
    ) as ext_key:
        winreg.SetValue(ext_key, None, winreg.REG_SZ, PROG_ID)

    base = f"Software\\Classes\\{PROG_ID}"
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, base) as prog_key:
        winreg.SetValue(prog_key, None, winreg.REG_SZ, "opip offline bundle")
        with winreg.CreateKey(prog_key, "DefaultIcon") as icon_key:
            winreg.SetValue(icon_key, None, winreg.REG_SZ, f"{sys.executable},0")
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

    keys = [
        rf"HKCU\Software\Classes\{PROG_ID}\shell",
        rf"HKCU\Software\Classes\{PROG_ID}",
        rf"HKCU\Software\Classes\{EXT}",
    ]
    for key in keys:
        subprocess.run(
            ["reg", "delete", key, "/f"],
            capture_output=True,
        )
    return True


def _set_verb(base, verb, label, command):
    import winreg

    path = f"{base}\\shell\\{verb}"
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, path) as verb_key:
        winreg.SetValue(verb_key, None, winreg.REG_SZ, label)
        with winreg.CreateKey(verb_key, "command") as cmd_key:
            winreg.SetValue(cmd_key, None, winreg.REG_SZ, command)
