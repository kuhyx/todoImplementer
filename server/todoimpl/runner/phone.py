"""Phone-last flow: `phone_ready.json` or `A: phone:` rests a run as `waiting_phone`."""

from __future__ import annotations

import os
import re
import subprocess
from typing import TYPE_CHECKING

from .files import read_json
from .stream import last_tag_line

if TYPE_CHECKING:
    from pathlib import Path

    from todoimpl.board.state import RunState

    from .stream import TurnResult

READY = "phone_ready.json"
SERIAL = "23181JEGR08034"
TRIED = "tried_attached"
ADB_TIMEOUT = 5.0
DEVICE_COLUMNS = 2
HANDS = "hands_nudged"
HANDS_ASK = r"\btaps?\b|open .* on the (pixel|phone)|real screen|\bpause\b|look at the phone|\bfeel\b"
PLUG_ASK = r"plug"
HANDS_NUDGE = (
    "(runner) Your last `A:` asks kuhy for phone hands-on work; do not ask kuhy. With the Pixel attached, "
    "do it yourself on your own slot: `~/.claude/scripts/phone_slot.sh acquire`, "
    "`phone_deploy.sh <app_dir> --release --slot`, `phone_vd.sh start <slot pkg>`, then tap/swipe/text/shot "
    "(slot data is sandboxed). A criterion that needs a human sense is `- [~] Cn: skipped: needs a human "
    "sense`. Without the Pixel, stage phone_ready.json and end `A: phone: <one line>`. Then end with "
    "`D:`, `Q:` or `A:`."
)
PHONE_TAG = re.compile(r"^[\s>*_#-]*A[*_]*:[*_]*\s*phone\s*:\s*(.*?)\s*$", re.IGNORECASE | re.MULTILINE)


def phone_line(text: str) -> str | None:  # noqa: D103
    found = PHONE_TAG.findall(text)
    return found[-1] if found else None


def asks_for_hands(text: str, *, plug: bool = True) -> bool:
    """Return whether the final `A:` line asks kuhy for hands-on phone work (`plug` counts when `plug`)."""
    found = last_tag_line(text)
    if found is None or found[0] != "A":
        return False
    pattern = f"{HANDS_ASK}|{PLUG_ASK}" if plug else HANDS_ASK
    return re.search(pattern, found[1], re.IGNORECASE) is not None


def hands_nudge(st: RunState, res: TurnResult, *, attached: bool, info: object) -> bool:
    """Queue ONE runner nudge when a live-check turn asked kuhy for phone hands-on work; True if queued.

    An unattached `A: phone:` is the staged wait for the cable, and an attached `A: phone:` is a lost phone
    (so `plug` is no hands-on ask there). The nudge turn keeps the attached prompt; a second ask just rests.
    """
    if res.tag != "A":
        st.extra.pop(HANDS, None)
        return False
    tagged = phone_line(res.text) is not None
    if st.extra.get(HANDS) or (tagged and not attached) or not asks_for_hands(res.text, plug=not tagged):
        return False
    st.extra[HANDS] = True
    st.extra["nudge"] = HANDS_NUDGE
    st.last_tag = None
    if attached and isinstance(info, dict):
        st.extra.update(phone_attached=True, waiting_phone=info)
    return True


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
    wait = {**info, "note": line} if line else dict(info)
    if attached and line is not None:
        # The phone was in for this turn, so its ask is not the cable: wait for a replug, not a requeue.
        wait[TRIED] = True
    st.extra["waiting_phone"] = wait
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
