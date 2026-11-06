"""Phone-last flow: `phone_ready.json` or `A: phone:` rests a run as `waiting_phone`."""

from __future__ import annotations

import os
import re
import subprocess
from typing import TYPE_CHECKING

from .files import read_json

if TYPE_CHECKING:
    from pathlib import Path

    from todoimpl.board.state import RunState

    from .stream import TurnResult

READY = "phone_ready.json"
SERIAL = "23181JEGR08034"
ADB_TIMEOUT = 5.0
DEVICE_COLUMNS = 2
PHONE_TAG = re.compile(r"^[\s>*_#-]*A[*_]*:[*_]*\s*phone\s*:\s*(.*?)\s*$", re.IGNORECASE | re.MULTILINE)


def phone_line(text: str) -> str | None:  # noqa: D103
    found = PHONE_TAG.findall(text)
    return found[-1] if found else None


def adb_command() -> str:  # noqa: D103
    return os.environ.get("TODOIMPL_ADB", "adb")


def after_turn(st: RunState, run_dir: Path, res: TurnResult) -> None:
    """Record or clear the phone wait after a turn; a staged check turns any non-question tag into `A`."""
    attached = bool(st.extra.pop("phone_attached", False))
    staged = read_json(run_dir / READY)
    line = phone_line(res.text)
    if attached and line is None:
        (run_dir / READY).unlink(missing_ok=True)
        staged = None
    if res.tag == "Q" or (line is None and not isinstance(staged, dict)):
        st.extra.pop("waiting_phone", None)
        return
    info = staged if isinstance(staged, dict) else st.extra.get("waiting_phone") or {}
    st.extra["waiting_phone"] = {**info, "note": line} if line else dict(info)
    res.tag = st.last_tag = "A"


def attached_serials(adb: str, timeout: float = ADB_TIMEOUT) -> set[str]:
    """Return the serials `adb devices` lists as `device`; no adb or a hang means none."""
    try:
        out = subprocess.run(  # noqa: S603
            [adb, "devices"], capture_output=True, text=True, timeout=timeout, check=False
        ).stdout
    except OSError, subprocess.TimeoutExpired:
        return set()
    rows = (line.split("\t") for line in out.splitlines()[1:])
    return {row[0] for row in rows if len(row) == DEVICE_COLUMNS and row[1].strip() == "device"}
