"""Detached processes for the e2e run: systemd-run --user units (pid + process group as the fallback)."""

from __future__ import annotations

import contextlib
import os
import signal
import socket
import subprocess
import time
from pathlib import Path


def free_port() -> int:
    """Return a currently free loopback port."""
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def launch(name: str, argv: list[str], env: dict[str, str], cwd: Path, log: Path) -> str:
    """Start argv detached with exactly env; return the handle ("unit:<name>" or "pid:<n>").

    systemd-run --user --collect keeps it alive past this call's scope (setsid would die with it); set
    E2E_NO_SYSTEMD=1 to use a plain detached process group instead.
    """
    if not os.environ.get("E2E_NO_SYSTEMD"):
        unit = f"todoimpl-e2e-{name}-{cwd.parent.name[-8:]}"
        cmd = [
            "systemd-run",
            "--user",
            "--collect",
            "--quiet",
            "--unit",
            unit,
            "--working-directory",
            str(cwd),
        ]
        cmd += ["-p", f"StandardOutput=append:{log}", "-p", f"StandardError=append:{log}"]
        cmd += [f"--setenv={key}={value}" for key, value in env.items()]
        if subprocess.run([*cmd, *argv], check=False, capture_output=True).returncode == 0:
            return f"unit:{unit}"
    with log.open("ab") as out:
        proc = subprocess.Popen(
            argv, cwd=cwd, env=env, stdout=out, stderr=subprocess.STDOUT, start_new_session=True
        )
    return f"pid:{proc.pid}"


def alive(handle: str) -> bool:
    """Report whether the process or unit is still running."""
    kind, _, ident = handle.partition(":")
    if kind == "unit":
        return (
            subprocess.run(["systemctl", "--user", "is-active", "--quiet", ident], check=False).returncode
            == 0
        )
    try:
        os.kill(int(ident), 0)
    except OSError:
        return False
    return True


def stop(handle: str) -> None:
    """Stop the unit or kill the process group; already gone is fine."""
    kind, _, ident = handle.partition(":")
    if kind == "unit":
        subprocess.run(["systemctl", "--user", "stop", ident], check=False, capture_output=True)
        return
    with contextlib.suppress(OSError):
        os.killpg(int(ident), signal.SIGTERM)


def wait_for(check: object, timeout: float, every: float = 0.3) -> bool:
    """Poll the callable until it returns truthy or the timeout passes."""
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if callable(check) and check():
            return True
        time.sleep(every)
    return False


def tail(path: Path, lines: int = 12) -> str:
    """Return the last lines of a log file (empty when missing)."""
    if not path.exists():
        return ""
    return "\n".join(path.read_text(encoding="utf-8", errors="replace").splitlines()[-lines:])
