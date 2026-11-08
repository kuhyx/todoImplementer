"""Desktop notification through notify-send; a missing binary or a failure is logged, never raised."""

from __future__ import annotations

import logging
import shutil
import subprocess

log = logging.getLogger("todoimpl.apikey")


def notify_send(title: str, text: str) -> bool:
    """Send a critical notification; False (logged) when notify-send is missing or exits non-zero."""
    binary = shutil.which("notify-send")
    if binary is None:
        log.warning("notify-send not found: skipping the desktop notification %r", title)
        return False
    done = subprocess.run(  # noqa: S603 - fixed argv, no shell
        [binary, "-u", "critical", title, text], capture_output=True, timeout=10, check=False
    )
    if done.returncode != 0:
        log.warning("notify-send failed (exit %s): %s", done.returncode, done.stderr[:200])
    return done.returncode == 0
