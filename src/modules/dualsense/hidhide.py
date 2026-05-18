"""HidHide auto-whitelist — Windows only.

If HidHideCLI.exe is reachable we register this process on HidHide's
allow-list so the cloaked DualSense is visible to hid.enumerate(). A
successful registration also tells the I/O loop to stay connected for
the rest of the session (no reconnect / no liveness watchdog), since
HidHide is the only thing that would have torn the handle down.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import sys
from pathlib import Path

log = logging.getLogger("fhds.dualsense.hidhide")


def _resolve_cli() -> str | None:
    if sys.platform != "win32":
        return None
    env = os.environ.get("HIDHIDE_CLI")
    if env and Path(env).is_file():
        return env
    on_path = shutil.which("HidHideCLI.exe")
    if on_path:
        return on_path
    pf = os.environ.get("ProgramFiles", r"C:\Program Files")
    standard = Path(pf) / "Nefarius Software Solutions" / "HidHide" / "x64" / "HidHideCLI.exe"
    return str(standard) if standard.is_file() else None


def _run(cli: str, *args: str) -> tuple[int, str]:
    try:
        proc = subprocess.run(
            [cli, *args],
            capture_output=True, text=True, timeout=5,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except (OSError, subprocess.TimeoutExpired) as e:
        return -1, str(e)
    return proc.returncode, (proc.stdout or "") + (proc.stderr or "")


_done = False
_detected = False
_whitelisted = False


def is_detected() -> bool:
    return _detected


def is_whitelisted() -> bool:
    return _whitelisted


def ensure_whitelisted() -> None:
    """Register this process on HidHide's whitelist when HidHide is installed.
    Idempotent; logs which of the three outcomes happened so the caller can
    pick reconnect vs. persistent mode."""
    global _done, _detected, _whitelisted
    if _done:
        return
    _done = True
    cli = _resolve_cli()
    if cli is None:
        return  # HidHide not installed — silent, normal mode.
    _detected = True
    exe = str(Path(sys.executable).resolve())
    rc, out = _run(cli, "--app-list")
    if rc == 0 and exe.lower() in out.lower():
        _whitelisted = True
        log.info("HidHide detected — app already on whitelist (reconnect setting honored)")
        return
    rc, _ = _run(cli, "--app-reg", exe)
    if rc == 0:
        _whitelisted = True
        log.info("HidHide detected — app added to whitelist (reconnect setting honored)")
        return
    log.warning("HidHide detected — whitelist failed; entering persistent mode "
                "(controller handle held open, reconnect setting bypassed)")
